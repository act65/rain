"""
Claim under test: a lender prefers a guarantee at equal interest, is indifferent at a premium of
(i + q) / (1 - q) - i on the unsecured part, and the borrower is still better off graduating. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain.provenance import run_provenance
from rain.record import Entry, graduated_credit

HERE = Path(__file__).parent
R, Q, PHI, DELTA, INTEREST = 0.05, 0.02, 0.01, 0.03, 0.05
SUNK = R / (R + DELTA)
BETA = 1 / (1 + R)
START, NEED, CYCLES = 100.0, 10_000.0, 400


def schedule(unsecured_rate, graduate=True):
    """(unsecured due, guaranteed due) per cycle for a borrower who keeps repaying."""
    log, plan = [], []
    for t in range(CYCLES):
        own = min(NEED, graduated_credit(log, "newcomer", "bank", START, 1 + unsecured_rate, SUNK)) if graduate else 0.0
        rest = NEED if (t == 0 or not graduate) else NEED - own
        plan.append((own, rest))
        # both loans are made in cycle t and repaid in cycle t + 1
        if rest > 1e-9:
            log.append(Entry("newcomer", "sam", rest, True, time=t + 1, fee_paid=PHI * rest, created=t))
        if own > 0:
            log.append(Entry("newcomer", "bank", own, True, time=t + 1, fee_paid=PHI * own, created=t))
    return plan


def lender_value(plan, unsecured_rate):
    """Expected present value to the lender: interest on what is repaid, less unsecured principal lost to shocks."""
    total = 0.0
    for t, (own, rest) in enumerate(plan):
        alive = ((1 - Q) * BETA) ** t
        total += alive * (INTEREST * rest / (1 + INTEREST)
                          + ((1 - Q) * unsecured_rate - Q) * own / (1 + unsecured_rate))
    return total


def simulate_lender(plan, unsecured_rate, n=400_000, seed=0):
    rng = np.random.default_rng(seed)
    shock = rng.geometric(Q, size=n) - 1  # the cycle whose loans are hit
    own = np.array([p[0] for p in plan])
    rest = np.array([p[1] for p in plan])
    disc = BETA ** np.arange(CYCLES)
    safe = disc * (INTEREST * rest / (1 + INTEREST) + unsecured_rate * own / (1 + unsecured_rate))
    hit = disc * (INTEREST * rest / (1 + INTEREST) - own / (1 + unsecured_rate))
    before = np.concatenate([[0.0], np.cumsum(safe)])
    capped = np.minimum(shock, CYCLES - 1)
    values = before[capped] + np.where(shock < CYCLES, hit[capped], safe[capped])
    return float(values.mean()), float(values.std() / np.sqrt(n))


def borrower_cost(own, rest, unsecured_rate):
    """What one cycle's borrowing costs the borrower beyond the principal: interest, and the guarantor's price."""
    return (unsecured_rate * own / (1 + unsecured_rate) + INTEREST * rest / (1 + INTEREST)
            + (Q * rest + PHI * rest * SUNK if rest > 1e-9 else 0.0))


def graduated_in(plan):
    return next((t for t, (_, rest) in enumerate(plan) if rest <= 1e-6), None)


def main():
    premium_rate = (INTEREST + Q) / (1 - Q)
    plans = {
        "a. guaranteed for ever": (schedule(INTEREST, graduate=False), INTEREST),
        "b. graduating, unsecured at 5%": (schedule(INTEREST), INTEREST),
        f"c. graduating, unsecured at {100 * premium_rate:.2f}%": (schedule(premium_rate), premium_rate),
    }
    rows = {}
    for seed, (name, (plan, rate)) in enumerate(plans.items()):
        mean, se = simulate_lender(plan, rate, seed=seed)
        rows[name] = dict(lender_value=lender_value(plan, rate), simulated=mean, standard_error=se,
                          graduates_in_cycle=graduated_in(plan),
                          borrower_cost_first_cycle=borrower_cost(*plan[0], rate), borrower_cost_cycle_100=borrower_cost(*plan[100], rate))
    base = rows["a. guaranteed for ever"]
    principal = NEED / (1 + INTEREST)
    guarantee_cost_rate = (INTEREST * principal + Q * NEED + PHI * NEED * SUNK) / principal
    # the unsecured rate at which a graduated borrower pays what the guarantee cost them
    lo, hi = INTEREST, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if borrower_cost(NEED, 0.0, mid) < base["borrower_cost_cycle_100"] else (lo, mid)
    speeds = {f"{100 * rate:.2f}%": graduated_in(schedule(rate)) for rate in (0.05, 0.06, premium_rate, lo)}

    out = dict(provenance=run_provenance(), parameters=dict(r=R, shock=Q, fee_rate=PHI, interest=INTEREST, sunk_fee_share=SUNK),
               premium_rate=premium_rate, arrangements=rows, guarantee_cost_rate=guarantee_cost_rate,
               borrower_indifferent_rate=lo, graduation_by_unsecured_rate=speeds)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Would a lender let the guarantor go? Results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         "| arrangement | lender's expected value | simulated | standard error | relative to (a) | guarantee gone in cycle | borrower's cost per cycle, at cycle 100 |",
         "|---|---|---|---|---|---|---|"]
    for name, r in rows.items():
        L.append(f"| {name} | {r['lender_value']:,.0f} | {r['simulated']:,.0f} | {r['standard_error']:.0f} | {r['lender_value'] / base['lender_value']:.3f} | "
                 f"{r['graduates_in_cycle'] if r['graduates_in_cycle'] is not None else 'never'} | {r['borrower_cost_cycle_100']:.1f} |")
    L += ["", f"The lender is indifferent at an unsecured rate of {100 * premium_rate:.2f}%. "
          f"A guarantee costs the borrower {100 * guarantee_cost_rate:.2f}% of the principal per loan; "
          f"a graduated borrower pays as much at an unsecured rate of {100 * lo:.2f}%.", "",
          "Cycle in which the guarantee is gone, by unsecured rate: " + ", ".join(f"{k}: {v}" for k, v in speeds.items()) + "."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
