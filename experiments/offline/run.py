"""
Claim under test: a payee who cannot see a payer's other notes should accept the payer's limit divided
by the number of places the payer could be; credit then grows offline only if notes owed at once are
read as their total; and that reading gives a ring nothing. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain.model import Economy
from rain.offline import split_limit
from rain.provenance import run_provenance
from rain.record import Entry, largest_amount_due, trusting, weigh

HERE = Path(__file__).parent
KAPPA, DELTA, PHI, FMIN, INTEREST = 0.04, 0.03, 0.01, 0.1, 0.05
RHO, FLOOR, TAIL, SHOCK = 0.10, 100.0, 1.0, 0.02
BELIEF = dict(risk_tolerance=RHO, floor=FLOOR, tail_index=TAIL, shock_rate=SHOCK)
K = (1 - SHOCK) / (1 - RHO)
EVIDENCE = 1_000.0  # what the payers of arms A, B, C and S have shown
LIMIT = largest_amount_due((((EVIDENCE, 1.0),),), **BELIEF)
STRANGER = largest_amount_due((), **BELIEF)
M = 5
PAYERS, SEEDS, WINDOWS = 100_000, 5, 30


def economy():
    return Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)


# --- default rates among payers drawn from the belief ---

def predicted_default_rate(total_owed):
    return 1 - (1 - SHOCK) * min(1.0, EVIDENCE / total_owed)


def simulated_default_rate(total_owed):
    rates = []
    for seed in range(SEEDS):
        rng = np.random.default_rng(seed)
        threshold = EVIDENCE / rng.random(PAYERS)  # P(c > x) = E / x
        pays = (total_owed <= threshold) & (rng.random(PAYERS) >= SHOCK)
        rates.append(1 - pays.mean())
    return float(np.mean(rates)), float(np.std(rates) / np.sqrt(SEEDS))


def exposure_row(per_payee, n):
    total = per_payee * n
    mean, se = simulated_default_rate(total)
    return dict(payees=n, per_payee=per_payee, total_owed=total, over_limit=total / LIMIT,
                default_rate=mean, standard_error=se, predicted=predicted_default_rate(total),
                attacker_takes=attack(per_payee, n))


# --- an attacker, through the model of the contracts ---

def attack(per_payee, n, default_on_lender_first=False, stale=True):
    """
    What a payer with a record of EVIDENCE takes from `n` payees who each accept `per_payee`, paying
    nothing. If `default_on_lender_first`, they first default on a loan of the whole limit from a
    lender on the chain; payees with a stale log have not seen it, payees with a fresh one refuse.
    Returns the goods and money taken, in units of LIMIT.
    """
    eco = economy()
    eco.add_agent("payer", money=EVIDENCE * 2)
    eco.add_agent("lender", money=1e7)
    for i in range(n):
        eco.add_agent(f"payee{i}", money=1e5)
    eco.repay_loan(eco.loan("payer", "lender", EVIDENCE, 0.0))  # the record
    assert abs(largest_amount_due(weigh(eco.log, "payer").repaid, **BELIEF) - LIMIT) < 1e-9
    eco.cycle += 1
    taken = 0.0
    if default_on_lender_first:
        principal = LIMIT / (1 + INTEREST)
        eco.default_loan(eco.loan("payer", "lender", principal, LIMIT - principal))
        taken += LIMIT
        eco.cycle += 1
    refused = eco.agents["payer"].delinquent and not stale
    eco.agents["payer"].money = 0.0  # gone before any note reaches the chain
    if not refused:
        before = sum(eco.agents[f"payee{i}"].money for i in range(n))
        for i in range(n):
            assert not eco.settle_note("payer", f"payee{i}", per_payee, issued=eco.cycle - 0.5)
        fees_lost = before - sum(eco.agents[f"payee{i}"].money for i in range(n))
        assert abs(fees_lost - n * max(FMIN, PHI * per_payee)) < 1e-6
        assert sum(1 for e in eco.log if e.promisor == "payer" and not e.kept) == n + default_on_lender_first
        taken += n * per_payee
    return taken / LIMIT


# --- growth of an honest payer's limit ---

def grow(m, j, concurrent, trust_between_payees=1.0, hub=False):
    """The limit payee 0 (or the hub) allows an honest payer, after each of WINDOWS windows."""
    eco = economy()
    eco.add_agent("pat", money=1e12)
    payees = [f"payee{i}" for i in range(m)]
    for name in payees:
        eco.add_agent(name, money=1e9)

    def limit(reader):
        trust = (lambda who: 1.0) if hub else trusting({reader: 1.0}, default=trust_between_payees)
        return largest_amount_due(weigh(eco.log, "pat", trust=trust, concurrent=concurrent).repaid, **BELIEF)

    limits = [limit(payees[0])]
    for w in range(WINDOWS):
        offers = [limit(p) / j if hub else split_limit(limit(p), m) for p in payees[:j]]
        eco.cycle += 1  # the sync
        for i, (p, amount) in enumerate(zip(payees, offers)):
            assert eco.settle_note("pat", p, amount, issued=w + 0.1 * (i + 1))
        limits.append(limit(payees[0]))
    return limits


def growth_row(label, **kw):
    limits = grow(**kw)
    return dict(case=label, limit_at_start=limits[0], limit_after=limits[-1],
                growth_per_window=float((limits[-1] / limits[-11]) ** 0.1), first_step=limits[1] / limits[0])


# --- washing with notes issued at once ---

AMOUNTS = np.logspace(2, 7, 2001)


def best_offer(trust_in_unknown, n, concurrent, split=True):
    """The largest offer, over the amount washed, that a ring of `n` confederates extracts, as a multiple of a stranger's."""
    best = 0.0
    for total in AMOUNTS:
        each = total / n if split else total
        log = [Entry("mallory", f"friend{i}", each, True, time=1, created=0, fee_paid=PHI * each) for i in range(n)]
        ev = weigh(log, "mallory", trust=lambda who: trust_in_unknown, concurrent=concurrent)
        best = max(best, largest_amount_due(ev.repaid, **BELIEF))
    return best / STRANGER


def main():
    arms = {
        "A. each payee accepts the whole limit": [exposure_row(LIMIT, n) for n in (1, 2, 5, 10)],
        f"B. each accepts the limit / {M}": [exposure_row(split_limit(LIMIT, M), n) for n in (1, 2, 4, 5, 10)],
        "C. hubs, each allowing the whole limit in all": [exposure_row(LIMIT, k) for k in (1, 2, 5)],
    }
    stale = {f"{n} payees, log stale": attack(split_limit(LIMIT, M), n, default_on_lender_first=True) for n in (1, 5)}
    stale["5 payees, log fresh"] = attack(split_limit(LIMIT, M), 5, default_on_lender_first=True, stale=False)
    stale["5 payees, limit / 6 (the lender counted as a place)"] = attack(split_limit(LIMIT, M + 1), 5, default_on_lender_first=True) \
        - 1 + 1 / (M + 1)  # the lender, too, lends a sixth

    growth = [
        growth_row("default reading, 1 payee", m=1, j=1, concurrent=False),
        growth_row("default reading, 5 of 5 payees", m=5, j=5, concurrent=False),
        growth_row("concurrent, 5 of 5, payees trust each other fully", m=5, j=5, concurrent=True),
        growth_row("concurrent, 4 of 5, full trust", m=5, j=4, concurrent=True),
        growth_row("concurrent, 5 of 5, trust 0.9", m=5, j=5, concurrent=True, trust_between_payees=0.9),
        growth_row("concurrent, 5 of 5, trust 0.5", m=5, j=5, concurrent=True, trust_between_payees=0.5),
        growth_row("concurrent, 2 of 2, trust 0.9", m=2, j=2, concurrent=True, trust_between_payees=0.9),
        growth_row("one hub, spent at 5 payees", m=5, j=5, concurrent=True, hub=True),
        growth_row("one hub, spent at 2 payees", m=5, j=2, concurrent=True, hub=True),
    ]

    washing = {}
    for t0 in (0.0, 0.5, 0.9):
        washing[str(t0)] = {
            "default reading, 1 confederate": best_offer(t0, 1, concurrent=False),
            **{f"concurrent, {n} confederates sharing the amount": best_offer(t0, n, concurrent=True) for n in (1, 2, 5)},
            **{f"concurrent, {n} confederates, the amount each": best_offer(t0, n, concurrent=True, split=False) for n in (2, 5)},
            "default reading, 5 confederates, the amount each": best_offer(t0, 5, concurrent=False, split=False),
        }

    out = dict(provenance=run_provenance(),
               parameters=dict(evidence=EVIDENCE, limit=LIMIT, stranger_limit=STRANGER, growth=K, places=M, payers=PAYERS, seeds=SEEDS,
                               windows=WINDOWS, belief=BELIEF),
               exposure=arms, stale_log=stale, growth=growth, washing=washing)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Offline: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"A payer who has shown {EVIDENCE:,.0f} has a limit of {LIMIT:,.1f}; a stranger, {STRANGER:.1f}.", ""]
    for name, rows in arms.items():
        L += [f"## {name}", "", "| payees (or hubs) | each accepts | owed in all, as a multiple of the limit | default rate | predicted | an attacker takes (limits) |",
              "|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['payees']} | {r['per_payee']:,.1f} | {r['over_limit']:.2f} | {100 * r['default_rate']:.2f}% (se {100 * r['standard_error']:.2f}) | "
                     f"{100 * r['predicted']:.2f}% | {r['attacker_takes']:.2f} |")
        L.append("")
    L += ["## S. A payer who has already defaulted on the chain", "", "| case | taken in all (limits) |", "|---|---|"]
    L += [f"| {k} | {v:.2f} |" for k, v in stale.items()]
    L += ["", f"## Growth of an honest payer's limit over {WINDOWS} windows", "",
          "| case | limit at the start | after | growth per window (last ten) | first step |", "|---|---|---|---|---|"]
    L += [f"| {g['case']} | {g['limit_at_start']:.1f} | {g['limit_after']:,.1f} | {g['growth_per_window']:.4f} | {g['first_step']:.4f} |" for g in growth]
    L += ["", "## Washing with notes issued at once: the largest offer extracted, as a multiple of a stranger's", ""]
    names = list(next(iter(washing.values())))
    L += ["| the bank's trust in unknown counterparties | " + " | ".join(names) + " |", "|" + "---|" * (len(names) + 1)]
    L += [f"| {t0} | " + " | ".join(f"{row[n]:,.2f}" for n in names) + " |" for t0, row in washing.items()]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
