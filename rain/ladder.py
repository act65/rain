"""
Progressive lending: how much to lend next, given what has been repaid.

Screening model. Each borrower has a private cost of defaulting, c (what their standing
is worth to them). They repay a loan when the amount due is at most c, except that with
probability q a shock makes them default regardless. Across borrowers c follows a Pareto
distribution with tail index a: P(c > x) = (x_min / x) ** a for x >= x_min. Repaying
an amount M therefore shows c >= M, and

    P(repay X | largest amount repaid is M, still the same person) = (1 - q) * (M / X) ** a   for X >= M.

A lender who tolerates a default probability rho should therefore let the amount due grow
by at most a factor k = ((1 - q) / (1 - rho)) ** (1 / a) over the largest amount repaid.

Incentive model. A borrower who stays on a ladder growing by k per loan, earning a surplus
`sigma` per unit borrowed, repays iff k >= (1 + i)(1 + r) / (1 + i + sigma). And someone who
climbs only in order to default at the top has paid more interest than they take iff
k <= 1 + i (for a long ladder).

See notes/bayesian-reputation.md.

None of this is part of the protocol. Rain records promises and what became of them; how
much to lend against a given record is for each lender or script to decide. This module is
one worked answer, for people building on Rain. `repayment_history` reads the record it needs
from the promise log.
"""

from __future__ import annotations

import math


def repay_probability(amount_due: float, largest_repaid: float, tail_index: float, shock_rate: float = 0.0,
                      still_same: float = 1.0, x_min: float = 0.0) -> float:
    """
    Probability that `amount_due` is repaid, given the largest amount this borrower has repaid.

    `still_same` is the probability that the borrower's type has not changed since that
    evidence (e.g. (1 - h) ** age); otherwise they are a fresh draw, known only to have c >= x_min.
    """
    def survival(threshold: float) -> float:
        if threshold <= 0 or amount_due <= threshold:
            return 1.0 if amount_due <= threshold else 0.0
        return (threshold / amount_due) ** tail_index

    return (1 - shock_rate) * (still_same * survival(largest_repaid) + (1 - still_same) * survival(x_min))


def screening_growth_factor(risk_tolerance: float, tail_index: float, shock_rate: float = 0.0) -> float:
    """
    k_max: the largest ratio (amount due) / (largest amount repaid) at which the probability
    of default stays within `risk_tolerance`. Requires risk_tolerance >= shock_rate.
    """
    if risk_tolerance < shock_rate:
        raise ValueError("No loan is this safe: shocks alone exceed the risk tolerance")
    return ((1 - shock_rate) / (1 - risk_tolerance)) ** (1 / tail_index)


def incentive_growth_factor(interest_rate: float, surplus_rate: float, r: float) -> float:
    """
    k_min: the slowest growth of loan size at which a borrower prefers to keep repaying.
    Staying is worth sigma * P * k / (1 + r - k) (the surplus on all later loans); leaving
    saves P (1 + i). Infinite if there is no surplus.
    """
    if surplus_rate <= 0:
        return math.inf
    return (1 + interest_rate) * (1 + r) / (1 + interest_rate + surplus_rate)


def exit_profit(first_loan: float, growth: float, interest_rate: float, steps: int, fee: float = 0.0) -> float:
    """
    Profit of a borrower who repays `steps - 1` loans growing by `growth` (paying interest
    and a fee on each) and defaults on loan number `steps`, with no use for the money borrowed.
    """
    loans = [first_loan * growth**j for j in range(steps)]
    return loans[-1] - interest_rate * sum(loans[:-1]) - fee * steps


def feasible_band(interest_rate: float, surplus_rate: float, r: float, risk_tolerance: float,
                  tail_index: float, shock_rate: float = 0.0):
    """
    (k_min, k_max) for the ladder's growth factor, or None if empty.
    k_max is the smaller of the lender's screening limit and the exit-scam limit 1 + i.
    """
    k_min = incentive_growth_factor(interest_rate, surplus_rate, r)
    k_max = min(screening_growth_factor(risk_tolerance, tail_index, shock_rate), 1 + interest_rate)
    return (k_min, k_max) if k_min <= k_max else None


# --- The lender's side: what a relationship is worth, and what to risk on a stranger ---

def repeat_value(interest_rate: float, shock_rate: float, r: float) -> float:
    """
    Present value to a lender, per unit of amount due, of lending the same amount every period
    to a borrower known to repay it, until a shock ends the relationship (the principal is then lost).
    """
    per_loan = ((1 - shock_rate) * interest_rate - shock_rate) / (1 + interest_rate)
    return per_loan / (1 - (1 - shock_rate) / (1 + r))


def stranger_value(first_due: float, opportunist_share: float, floor: float, tail_index: float,
                   interest_rate: float, shock_rate: float, r: float) -> dict:
    """
    What a lender expects from a stranger who is offered `first_due` and, if they repay, the same
    again every period. A share `opportunist_share` of strangers take the first loan and vanish;
    the rest have thresholds Pareto(floor, tail_index).

    Returns `first_loan` (the expected profit of the first loan alone), `relationship` (the whole
    present value) and `price_of_information` (what the first loan is expected to lose, if anything).
    """
    principal = first_due / (1 + interest_rate)
    repay = (1 - shock_rate) * min(1.0, (floor / first_due) ** tail_index)
    v = repeat_value(interest_rate, shock_rate, r)
    genuine_first = repay * interest_rate * principal - (1 - repay) * principal
    first = -opportunist_share * principal + (1 - opportunist_share) * genuine_first
    relationship = first + (1 - opportunist_share) * repay * v * first_due / (1 + r)
    return dict(first_loan=first, relationship=relationship, price_of_information=max(0.0, -first))


def opportunist_share_bounds(interest_rate: float, shock_rate: float, r: float) -> tuple:
    """
    (lo, hi). With more than `lo` of strangers being opportunists a first loan loses money in
    expectation; with more than `hi` it is not worth making even for the relationships it starts.
    Between the two, the expected loss on the first loan is the price of learning who is genuine.
    """
    margin = (1 - shock_rate) * interest_rate - shock_rate
    worth = repeat_value(interest_rate, shock_rate, r) * (1 + interest_rate)
    return margin / (1 + margin), worth / (1 + worth)


def growth_pays(tail_index: float, interest_rate: float, shock_rate: float, r: float) -> bool:
    """
    Whether a profit-maximising lender, far below what the borrower can use, raises the loan at all
    after a repayment. Raising it risks the whole principal to learn whether the threshold is higher;
    that pays only when thresholds are heavy-tailed enough: (1 - q)(1 - a)(1 + i)(1 + v / (1 + r)) > 1.
    """
    v = repeat_value(interest_rate, shock_rate, r)
    return (1 - shock_rate) * (1 - tail_index) * (1 + interest_rate) * (1 + v / (1 + r)) > 1


def identity_bound(identity_cost: float, fee_rate: float, interest_rate: float) -> float:
    """
    The largest first amount due at which taking it and vanishing does not pay for a new identity
    that costs `identity_cost`: the principal, less the protocol fee, is no more than the identity.
    """
    return identity_cost / (1 / (1 + interest_rate) - fee_rate)


def repayment_history(engine_contract, borrower: str, asset: str = None, from_block: int = 0, to_block: int = None) -> dict:
    """
    What the CalculusEngine's promise log says about `borrower` as a promisor:
    how many promises they kept and broke, and the largest amount they have kept a promise for
    (optionally only promises in `asset`). Amounts are in the asset's base units.
    """
    borrower = str(borrower)
    kept = broken = largest_kept = 0
    for event_name, is_kept in (("PromiseFulfilled", True), ("PromiseDefaulted", False)):
        event = getattr(engine_contract, event_name)
        stop = event.chain_manager.blocks.height if to_block is None else to_block
        for log in event.range(from_block, stop + 1):
            promise = engine_contract.promises(log.event_arguments["promiseId"])
            promisor, promise_asset, amount = promise[1], promise[3], promise[4]
            if str(promisor) != borrower or (asset is not None and str(promise_asset) != str(asset)):
                continue
            if is_kept:
                kept += 1
                largest_kept = max(largest_kept, amount)
            else:
                broken += 1
    return dict(kept=kept, broken=broken, largest_kept=largest_kept)


# --- What a default costs someone on a ladder ---

def ladder_default_account(
    rung: int, first_loan: float, growth: float, cap: float, interest_rate: float, surplus_rate: float, r: float,
    fee_rate: float, min_fee: float, point_price: float, decay_rate: float,
    restart: bool = True, identity_cost: float = 0.0, other_value: float = 0.0, horizon: int = 3000,
) -> dict:
    """
    The full account of defaulting on loan number `rung` (from 0) of a ladder, against repaying it
    and carrying on. Loans grow by `growth` from `first_loan` up to `cap`; one loan per cycle.

    The defaulter keeps the amount due. They lose:
      - `dividends`: all their reputation (bonded and destroyed) and the reward for this loan,
        each point worth point_price * delta / (r + delta);
      - `access`: the difference between carrying on up the ladder and what they can do instead,
        which is to start again from the first rung as a new identity (`restart`, at `identity_cost`)
        or nothing at all. Each loan is worth its surplus, less its fee, plus the dividends on the
        reputation the fee buys;
      - `other`: anything else good standing is worth that a new identity would not have
        (`other_value`: roles or services gated by reputation), as a present value.

    Returns the parts and `gain` = kept - dividends - access - other. Default pays when gain > 0.
    """
    keep = decay_rate / (r + decay_rate)
    v = point_price * keep

    def loan(n):
        return min(first_loan * growth**n, cap)

    def fee(n):
        return max(min_fee, fee_rate * loan(n) * (1 + interest_rate))

    def worth(n):  # net value of taking and repaying loan n
        return surplus_rate * loan(n) - fee(n) * (1 - keep)

    held = sum(fee(m) / point_price * (1 - decay_rate) ** (rung - m) for m in range(rung))
    dividends = v * (held + fee(rung) / point_price)
    carry_on = sum(worth(rung + j) / (1 + r) ** j for j in range(1, horizon))
    start_again = (sum(worth(j - 1) / (1 + r) ** j for j in range(1, horizon)) - identity_cost) if restart else 0.0
    access = carry_on - max(0.0, start_again)
    kept = loan(rung) * (1 + interest_rate)
    return dict(loan=loan(rung), kept=kept, reputation=held, dividends=dividends, access=access, other=other_value,
                gain=kept - dividends - access - other_value)
