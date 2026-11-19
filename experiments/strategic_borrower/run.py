"""
Claim under test: the threshold model follows from a borrower who chooses. Whether they repay a
loan that will be offered again depends on their return and not on its size; their threshold is
their capacity, scaled; opportunists are borrowers whose return is low. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain import ladder
from rain.provenance import run_provenance

HERE = Path(__file__).parent
Q, R, PHI, KEEP = 0.02, 0.05, 0.01, 0.375
BETA = 1 / (1 + R)
HORIZON = 4000


def period_flows(principal, capacity, sigma, interest):
    """(cash at the start of a period, cost of repaying at its end), for one loan."""
    due = principal * (1 + interest)
    start = (sigma + interest) * min(principal, capacity) - PHI * due  # earnings less the fee (the principal is handled below)
    repay = due * (1 - KEEP * PHI)  # the repayment, less the dividends the kept promise's reputation will bring
    return start, repay


def value_of_repaying_for_ever(principal, capacity, sigma, interest):
    """Expected present value at the start of a loan, for a borrower who always repays. By direct summation."""
    start, repay = period_flows(principal, capacity, sigma, interest)
    total, alive = 0.0, 1.0
    for t in range(HORIZON):
        # in hand: the principal. No shock: repay out of it. Shock: it is lost.
        total += alive * BETA**t * (start + (1 - Q) * (principal - repay))
        alive *= 1 - Q
    return total


def repays(principal, capacity, sigma, interest):
    """Does a borrower holding the principal prefer repaying (and carrying on) to keeping it?"""
    _, repay = period_flows(principal, capacity, sigma, interest)
    return BETA * value_of_repaying_for_ever(principal, capacity, sigma, interest) >= repay


def cutoff_return(principal, interest, capacity=1e12):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if repays(principal, capacity, mid, interest) else (mid, hi)
    return hi


def cutoff_principal(capacity, sigma, interest):
    lo, hi = capacity, capacity * 100
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if repays(mid, capacity, sigma, interest) else (lo, mid)
    return lo


def monte_carlo(principal, sigma, interest, n=400_000, seed=0):
    """Independent check of the expected value: simulate the shock time of each borrower who always repays."""
    rng = np.random.default_rng(seed)
    start, repay = period_flows(principal, 1e12, sigma, interest)
    periods = rng.geometric(Q, size=n)  # the period in which the shock comes (1-based)
    t = np.arange(600)[None, :]
    live = t < periods[:, None]  # periods entered
    last = t == (periods[:, None] - 1)  # the period that ends in the shock
    flows = live * (start + np.where(last, 0.0, principal - repay))
    values = (flows * BETA**t).sum(axis=1)
    return float(values.mean()), float(values.std() / np.sqrt(n))


def climb(sigma, interest=0.05, first=43.6, floor=100.0):
    """A borrower's best response to: dues rising by 1 + i from `first` to `floor`, then `floor` for ever. Backward induction."""
    dues = [first]
    while dues[-1] * (1 + interest) < floor:
        dues.append(dues[-1] * (1 + interest))
    dues.append(floor)
    principals = [d / (1 + interest) for d in dues]

    def step(principal, value_next):
        start, repay = period_flows(principal, 1e12, sigma, interest)
        stay = -repay + BETA * value_next
        return start + (1 - Q) * (principal + max(stay, 0.0)), stay >= 0

    at_floor_repaying = value_of_repaying_for_ever(principals[-1], 1e12, sigma, interest)
    start, repay = period_flows(principals[-1], 1e12, sigma, interest)
    floor_repays = BETA * at_floor_repaying >= repay
    value = at_floor_repaying if floor_repays else start + (1 - Q) * principals[-1]
    decisions = [floor_repays]
    for principal in reversed(principals[:-1]):
        value, stays = step(principal, value)
        decisions.append(stays)
    decisions.reverse()
    first_default = next((n for n, stays in enumerate(decisions) if not stays), None)
    interest_received = sum(interest * p for p in principals[:first_default]) if first_default is not None else None
    lender_cash = None if first_default is None else interest_received - principals[first_default]
    return dict(rungs=len(dues), defaults_on_loan=None if first_default is None else first_default + 1,
                lender_cash=lender_cash, first_principal=principals[0])


def main():
    star = ladder.repay_surplus_threshold(0.05, Q, R, PHI, KEEP)
    p1 = dict(formula=star, cutoff_at_100=cutoff_return(100.0, 0.05), cutoff_at_10000=cutoff_return(10_000.0, 0.05),
              discount_plus_shock=R + Q)
    mc = []
    for sigma in (0.03, 0.079, 0.15):
        mean, se = monte_carlo(1000.0, sigma, 0.05)
        mc.append(dict(sigma=sigma, summation=value_of_repaying_for_ever(1000.0, 1e12, sigma, 0.05), simulated=mean, standard_error=se))

    p2 = []
    for sigma in (0.10, 0.15, 0.25):
        found = cutoff_principal(1000.0, sigma, 0.05)
        formula = ladder.capacity_threshold(1000.0, sigma, 0.05, Q, R, PHI, KEEP)
        p2.append(dict(sigma=sigma, threshold_over_capacity=found / 1000.0, formula=formula / 1000.0))

    p4 = {str(sigma): climb(sigma) for sigma in (0.0, 0.01, 0.03, 0.06, 0.10)}

    p5 = []
    for interest in (0.025, 0.05, 0.10):
        s = ladder.repay_surplus_threshold(interest, Q, R, PHI, KEEP)
        p5.append(dict(interest=interest, formula=s, cutoff=cutoff_return(1000.0, interest), gross=s + interest))

    out = dict(provenance=run_provenance(), parameters=dict(shock=Q, r=R, fee_rate=PHI, fee_returned=KEEP),
               return_threshold=p1, monte_carlo=mc, capacity=p2, climb=p4, by_interest=p5)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# A borrower who chooses: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         "## 1. The return at which a borrower repays a loan that will be offered again", "",
         f"Formula: {100 * star:.2f}%. Found by comparing the two strategies: {100 * p1['cutoff_at_100']:.2f}% at a principal of 100, "
         f"{100 * p1['cutoff_at_10000']:.2f}% at 10,000. Discount rate plus shock rate: {100 * (R + Q):.0f}%.", "",
         "Value of always repaying (principal 1,000), by summation and by simulating shock times:", "",
         "| net return | summation | simulated | standard error |", "|---|---|---|---|"]
    L += [f"| {100 * r['sigma']:.1f}% | {r['summation']:,.1f} | {r['simulated']:,.1f} | {r['standard_error']:.1f} |" for r in mc]
    L += ["", "## 2. Above capacity: the largest principal still repaid, over capacity", "", "| net return | found | formula |", "|---|---|---|"]
    L += [f"| {100 * r['sigma']:.0f}% | {r['threshold_over_capacity']:.3f} | {r['formula']:.3f} |" for r in p2]
    L += ["", "## 4. The screening climb (43.6 rising 5% a loan to 100, then 100 for ever)", "",
          "| net return | defaults on loan | lender's cash from this borrower | first principal |", "|---|---|---|---|"]
    for sigma, r in p4.items():
        which = "never" if r["defaults_on_loan"] is None else f"{r['defaults_on_loan']} of {r['rungs']}"
        cash = "-" if r["lender_cash"] is None else f"{r['lender_cash']:+.1f}"
        L.append(f"| {100 * float(sigma):.0f}% | {which} | {cash} | {r['first_principal']:.1f} |")
    L += ["", "## 5. By interest rate", "", "| interest | net return needed (formula) | found | gross return needed |", "|---|---|---|---|"]
    L += [f"| {100 * r['interest']:.1f}% | {100 * r['formula']:.2f}% | {100 * r['cutoff']:.2f}% | {100 * r['gross']:.1f}% |" for r in p5]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
