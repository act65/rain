"""
Reading the promise log as evidence: one reader's belief about one person.

The protocol keeps a true record of promises and makes each entry cost a fee. It cannot say
how much an entry is worth as evidence, because that depends on who is reading. A promise
kept to someone the reader has reason to think is independent of the promisor is evidence
about the promisor. A promise kept to a confederate is evidence of nothing but the fee. So
the reader supplies `trust`: for each counterparty, the probability that it is independent
of the person being judged. The on-chain counters (`RainReputation.reputationScores`,
`brokenScores`) are what this module computes for a reader who trusts everyone.

Two beliefs are computed from the same weighed record:

  - reliability, the chance the next promise is kept: the two counters of
    notes/bayesian-reputation.md, each kept promise counted at its credence;
  - the threshold, how large a promise they would keep: the model of `rain.ladder`, in
    which a person keeps promises up to a private amount c, Pareto distributed across
    people. A repayment of M shows c >= M only if it was genuine, which is where the
    credence enters (`threshold_survival`).

Credence. An entry counts with credence trust(counterparty) * retention ** age: the chance
that the counterparty was independent and that the promisor is still the person who kept it.
Broken promises count in full whoever they were to: nobody can be made to default (a script
acts for a user only with their consent), and a default to a confederate costs the defaulter.

Independence. Counterparties are treated as independent pieces of evidence unless `group`
maps them to the same key. Many identities controlled by one person are one piece of
evidence, and the reader has to know that (or give unknown identities no trust at all):
see experiments/collusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class Entry:
    """One resolved promise. `time` is in whatever unit the log uses (blocks on a chain, cycles in the model)."""
    promisor: str
    promisee: str
    amount: float
    kept: bool
    time: float = 0.0
    fee_paid: float = 0.0
    asset: Optional[str] = None


Trust = Union[None, Mapping[str, float], Callable[[str], float]]
Repaid = Tuple[Tuple[float, float], ...]  # (amount, credence) pairs


@dataclass(frozen=True)
class Evidence:
    """A person's record as one reader weighs it."""
    kept: float  # weight of kept promises, each at its credence
    broken: float  # weight of broken promises, faded but otherwise in full
    repaid: Tuple[Repaid, ...]  # per independent group of counterparties: the amounts repaid and the credence of each

    def reliability(self, prior_kept: float, prior_broken: float) -> float:
        """The estimated chance that the next promise is kept, for a prior of `prior_kept` to `prior_broken`."""
        return (prior_kept + self.kept) / (prior_kept + prior_broken + self.kept + self.broken)

    @property
    def largest_repaid(self) -> float:
        """The largest amount repaid to anyone, at any credence above zero (what a reader who trusts everyone uses)."""
        return max((amount for group in self.repaid for amount, _ in group), default=0.0)


def trusting(known: Mapping[str, float], default: float = 0.0) -> Callable[[str], float]:
    """A trust function: the credence given for each known counterparty, and `default` for everyone else."""
    known = {str(k): v for k, v in known.items()}
    return lambda counterparty: known.get(str(counterparty), default)


def by_fee(point_price: float) -> Callable[[Entry], float]:
    """Weighs a promise by the fee paid on it, in reputation points: the unit of the on-chain counters."""
    return lambda entry: entry.fee_paid / point_price


def _trust_function(trust: Trust) -> Callable[[str], float]:
    if trust is None:
        return lambda counterparty: 1.0
    if callable(trust):
        return trust
    return trusting(trust)


def _frontier(pairs: Iterable[Tuple[float, float]]) -> Repaid:
    """Drops repayments that a larger one, at least as credible, makes redundant. Sorted by amount."""
    kept: List[Tuple[float, float]] = []
    for amount, credence in sorted(pairs, reverse=True):  # largest first
        if credence > 0 and (not kept or credence > kept[-1][1]):
            kept.append((amount, credence))
    return tuple(reversed(kept))


def weigh(
    entries: Iterable[Entry], subject: str, trust: Trust = None, *,
    group: Optional[Callable[[str], Hashable]] = None, now: Optional[float] = None, retention: float = 1.0,
    asset: Optional[str] = None, weight: Optional[Callable[[Entry], float]] = None,
) -> Evidence:
    """
    The record of `subject` as a promisor, as a reader with this `trust` weighs it.

    trust: the probability that a counterparty is independent of the subject. None trusts
        everyone (the on-chain reading); a mapping gives the listed counterparties their value
        and everyone else none; or any function of the counterparty.
    group: maps counterparties to the same key when they are one piece of evidence.
    now, retention: an entry of age `now - time` keeps `retention ** age` of its credence
        (`now` defaults to the latest entry's time).
    asset: only promises in this asset.
    weight: the weight of one promise in the two counters (default 1 each; `by_fee` for the on-chain unit).
    """
    subject = str(subject)
    trust_of = _trust_function(trust)
    mine = [e for e in entries if str(e.promisor) == subject and (asset is None or str(e.asset) == str(asset))]
    if now is None:
        now = max((e.time for e in mine), default=0.0)

    kept = broken = 0.0
    groups: Dict[Hashable, List[Tuple[float, float]]] = {}
    for e in mine:
        fade = retention ** max(0.0, now - e.time)
        w = 1.0 if weight is None else weight(e)
        if not e.kept:
            broken += fade * w
            continue
        credence = min(1.0, max(0.0, trust_of(str(e.promisee)))) * fade
        kept += credence * w
        key = str(e.promisee) if group is None else group(str(e.promisee))
        groups.setdefault(key, []).append((float(e.amount), credence))
    repaid = tuple(g for g in (_frontier(pairs) for pairs in groups.values()) if g)
    return Evidence(kept=kept, broken=broken, repaid=repaid)


# --- The threshold belief: how large a promise would they keep? ---

def _doubt(repaid: Sequence[Repaid], c: float) -> float:
    """
    The likelihood of the record if the person's threshold is `c`, relative to a threshold above
    every amount repaid. A group's repayments above `c` must all have been empty; the chance of
    that is one minus the most credible of them.
    """
    doubt = 1.0
    for group in repaid:
        doubt *= 1.0 - max((credence for amount, credence in group if amount > c), default=0.0)
    return doubt


def threshold_survival(amount: float, repaid: Sequence[Repaid], floor: float, tail_index: float) -> float:
    """
    P(threshold >= amount | record). Before any record the threshold is Pareto:
    P(c > x) = (floor / x) ** tail_index for x >= floor. Each repayment of M with credence t
    multiplies the likelihood of thresholds below M by (1 - t).

    With one repayment at credence 1 this is (M / amount) ** tail_index above M and 1 below it
    (`rain.ladder.repay_probability` without shocks). With no record it is the prior.
    """
    def prior_survival(x: float) -> float:
        return 1.0 if x <= floor else (floor / x) ** tail_index

    cuts = sorted({floor, *(a for group in repaid for a, _ in group if a > floor)})
    total = above = 0.0
    for lo, hi in zip(cuts, cuts[1:] + [float("inf")]):
        mass = prior_survival(lo) - (0.0 if hi == float("inf") else prior_survival(hi))
        likelihood = _doubt(repaid, lo)  # constant on [lo, hi): no repaid amount lies strictly inside
        total += mass * likelihood
        if hi > amount:
            inside = prior_survival(max(lo, amount)) - (0.0 if hi == float("inf") else prior_survival(hi))
            above += inside * likelihood
    return above / total if total > 0 else 0.0


def repay_probability(amount: float, repaid: Sequence[Repaid], floor: float, tail_index: float,
                      shock_rate: float = 0.0) -> float:
    """The chance a promise of `amount` is kept: the threshold is at least that, and no shock intervenes."""
    return (1.0 - shock_rate) * threshold_survival(amount, repaid, floor, tail_index)


def largest_amount_due(repaid: Sequence[Repaid], risk_tolerance: float, floor: float, tail_index: float,
                       shock_rate: float = 0.0) -> float:
    """
    The largest amount a reader who accepts a `risk_tolerance` chance of default can let this
    person owe. Zero if shocks alone exceed the tolerance. With no record it is
    `floor * rain.ladder.screening_growth_factor(...)`: what a stranger is offered.
    """
    target = 1.0 - risk_tolerance

    def ok(x: float) -> bool:
        return repay_probability(x, repaid, floor, tail_index, shock_rate) >= target

    if not ok(floor):
        return 0.0
    lo, hi = floor, 2.0 * max([floor] + [a for group in repaid for a, _ in group])
    while ok(hi):
        lo, hi = hi, 2.0 * hi
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


# --- Credit that cannot be manufactured: a record is worth what it cost ---

def graduated_credit(
    entries: Sequence[Entry], subject: str, reader: str, start: float, growth: float, sunk_fee_share: float,
    asset: Optional[str] = None,
) -> float:
    """
    The largest amount due `reader` can accept from `subject` unsecured, by a rule that no ring of
    confederates can profit from whatever the reader believes about anyone:

        credit = min( evidence,  growth * own + cost since )

      - `own` is the largest amount the subject has repaid to the reader itself (if none, the
        first term is `start`, what the reader would lend a stranger);
      - `cost since` is what the subject has sunk in fees on kept promises after that repayment
        (before it, if there is none): `sunk_fee_share` of each fee, the part that does not come
        back as dividends. A record is worth as credit what it cost to make;
      - `growth` is at most 1 + the interest rate, so that repaying in order to default later
        returns nothing (the exit bound of `rain.ladder`);
      - `evidence` is the largest amount the subject has repaid to anyone, never less than `start`:
        if they are genuine it is what they have shown they are good for, and the other term
        makes it unprofitable to be anything else.

    A newcomer with a guarantor builds `evidence` at once and `cost` with every loan, and so
    outgrows the guarantor. See experiments/graduation.
    """
    subject, reader = str(subject), str(reader)
    kept = [e for e in entries if str(e.promisor) == subject and e.kept and (asset is None or str(e.asset) == str(asset))]
    evidence = max([start] + [float(e.amount) for e in kept])
    own = [i for i, e in enumerate(kept) if str(e.promisee) == reader]
    if own:
        last = max(own, key=lambda i: (kept[i].amount, i))  # the largest repayment to the reader; the latest of equals
        base, since = growth * float(kept[last].amount), kept[last + 1:]
    else:
        base, since = float(start), kept
    cost = sunk_fee_share * sum(float(e.fee_paid) for e in since)
    return min(evidence, base + cost)


# --- Reading a chain ---

def read_entries(engine_contract: Any, from_block: int = 0, to_block: Optional[int] = None) -> List[Entry]:
    """Every promise resolved in the (inclusive) block range of a CalculusEngine's log, in chain order. `time` is the block."""
    entries = []
    for event_name, kept in (("PromiseFulfilled", True), ("PromiseDefaulted", False)):
        event = getattr(engine_contract, event_name)
        stop = event.chain_manager.blocks.height if to_block is None else to_block
        for log in event.range(from_block, stop + 1):  # `range` excludes its stop block
            p = engine_contract.promises(log.event_arguments["promiseId"])
            entries.append((log.block_number, log.log_index, Entry(
                promisor=str(p[1]), promisee=str(p[2]), asset=str(p[3]), amount=p[4], kept=kept,
                time=log.block_number, fee_paid=p[7],
            )))
    return [entry for _, _, entry in sorted(entries, key=lambda x: (x[0], x[1]))]
