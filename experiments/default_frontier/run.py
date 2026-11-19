"""
Claim under test: `rain.economics.max_safe_loan` gives the loan size at which a borrower is
indifferent between repaying and defaulting, as measured by simulating each strategy.
See README.md for the predictions.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

from rain import economics as ec
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
M, R_DISC, INTEREST = 1.5, 0.05, 0.05
YIELD = 0.004
WORLD_REP = 1e9  # passive holders, so that one borrower does not move the dividend per point
HORIZON = 400  # (1.05)^-400 ~ 3e-9


def present_value(strategy: str, principal: float, reputation: float, bond: float, v: float, sigma: float) -> float:
    """Discounted change in the borrower's money, from the moment the current loan falls due."""
    eco = Economy(fee=ec.keeper_fee(v, M), yield_rate=YIELD)
    eco.add_agent("world", reputation=WORLD_REP)
    eco.add_agent("lender", money=1e15)
    eco.add_agent("borrower", money=1e12, reputation=reputation)
    eco.donate(v * R_DISC * eco.total_reputation / YIELD)  # treasury sized so that a point is worth v
    borrower = eco.agents["borrower"]

    loan = eco.loan("borrower", "lender", principal, INTEREST * principal, bond)  # sunk: already funded
    before = borrower.money
    if strategy == "default":
        eco.default_loan(loan)
    else:
        eco.repay_loan(loan)
    pv = borrower.money - before

    for t in range(1, HORIZON + 1):
        before = borrower.money
        eco.pay_dividend()  # reputation held at the end of the last cycle earns this cycle's dividend
        if strategy == "continue":
            loan = eco.loan("borrower", "lender", principal, INTEREST * principal, bond)
            borrower.money += (sigma + INTEREST) * principal  # what the borrowed capital earned
            eco.repay_loan(loan)
        pv += (borrower.money - before) / (1 + R_DISC) ** t
    return pv


def simulated_default_gain(principal, reputation, bond, v, sigma):
    honest = max(present_value(s, principal, reputation, bond, v, sigma) for s in ("continue", "stop"))
    return present_value("default", principal, reputation, bond, v, sigma) - honest


def simulated_max_safe_loan(reputation, bond, v, sigma):
    lo, hi = 0.0, 1.0
    while simulated_default_gain(hi, reputation, bond, v, sigma) <= 0:
        hi *= 2
        if hi > 1e9:
            return math.inf
    for _ in range(50):
        mid = (lo + hi) / 2
        if simulated_default_gain(mid, reputation, bond, v, sigma) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def part_a():
    rows = []
    grid = itertools.product([200, 1000, 5000], [0.2, 1.0], [0.05, 0.3077], [0.0, 0.03, 0.045])
    for reputation, bond_fraction, v, sigma in grid:
        bond = bond_fraction * reputation
        formula = ec.max_safe_loan(INTEREST, reputation, bond, v, sigma, M, R_DISC)
        simulated = simulated_max_safe_loan(reputation, bond, v, sigma)
        rows.append(dict(reputation=reputation, bond=bond, v=v, sigma=sigma, formula=formula, simulated=simulated,
                         relative_error=abs(simulated - formula) / formula))
    return rows


def part_b():
    """P* / (v * R): how many points' worth of credit one point of reputation backs."""
    rows = []
    for reputation in (100, 1000, 10000):
        for bond_fraction in (0.1, 0.5, 1.0):
            for sigma_over_r in (0.0, 0.5, 0.9, 1.0):
                p = ec.max_safe_loan(INTEREST, reputation, bond_fraction * reputation, 1.0, sigma_over_r * R_DISC, M, R_DISC)
                rows.append(dict(reputation=reputation, bond_fraction=bond_fraction, sigma_over_r=sigma_over_r,
                                 safe_loan_per_point_in_v=p / reputation))
    return rows


def part_c():
    v_demo = ec.point_value(5, 325, R_DISC)
    p_demo = ec.max_safe_loan(INTEREST, 100, 50, v_demo, 0.0, M, R_DISC)
    return dict(
        v_demo=v_demo, demo_safe_loan=p_demo, demo_loan=1000, oversize_factor=1000 / p_demo,
        demo_gain_from_default=ec.default_gain(1000, INTEREST, 100, 50, v_demo, 0.0, M, R_DISC),
        system_credit_over_treasury=YIELD / R_DISC,
    )


def control():
    """Worthless reputation, no surplus: defaulting must pay at every loan size."""
    return {str(p): simulated_default_gain(p, 1000, 1000, 0.0, 0.0) for p in (0.01, 1, 100)}


def main():
    a, b, c, ctl = part_a(), part_b(), part_c(), control()
    results = dict(provenance=run_provenance(), part_a=a, part_b=b, part_c=c, control=ctl)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(results, indent=1))

    worst = max(r["relative_error"] for r in a)
    lines = ["# Default-rationality frontier: results", "",
             f"Commit `{results['provenance']['commit_short']}` (dirty: {results['provenance']['dirty']}), {results['provenance']['utc']}.", "",
             "## A. Formula against simulation", "",
             f"{len(a)} grid points; worst relative error {worst:.2e}.", "",
             "| R | bond | v | sigma | P* formula | P* simulated | rel. error |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['reputation']} | {r['bond']:.0f} | {r['v']} | {r['sigma']} | {r['formula']:.3f} | {r['simulated']:.3f} | {r['relative_error']:.1e} |" for r in a]
    lines += ["", "## B. Safe loan per point of reputation, in units of v", "",
              "| R | bond / R | sigma / r = 0 | 0.5 | 0.9 | 1.0 |", "|---|---|---|---|---|---|"]
    for reputation in (100, 1000, 10000):
        for bf in (0.1, 0.5, 1.0):
            cells = [next(r["safe_loan_per_point_in_v"] for r in b if (r["reputation"], r["bond_fraction"], r["sigma_over_r"]) == (reputation, bf, s)) for s in (0.0, 0.5, 0.9, 1.0)]
            lines.append(f"| {reputation} | {bf} | " + " | ".join(f"{x:.3f}" for x in cells) + " |")
    lines += ["", "## C. The demo loan and system-wide credit", "",
              f"- v in the demo: {c['v_demo']:.4f} DMD per point",
              f"- largest safe loan for the demo borrower (R = 100, bond 50): {c['demo_safe_loan']:.2f} DMD",
              f"- the demo loan is 1000 DMD: {c['oversize_factor']:.1f} times too large; defaulting on it gains {c['demo_gain_from_default']:.2f} DMD",
              f"- credit all reputation can safely back, as a fraction of the treasury (no surplus): {c['system_credit_over_treasury']:.3f}",
              "", "## Control (v = 0, no surplus): gain from defaulting", ""]
    lines += [f"- P = {p}: {g:+.4f}" for p, g in ctl.items()]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
