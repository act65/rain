"""
Claim under test: the profit from bonding all reputation and defaulting on everything is
`(ell - v) * R0 + n * g * (ell - m * v)`. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain import economics as ec
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
M, R_DISC, YIELD = 1.5, 0.05, 0.004
R0, LENDERS = 100.0, 4
V_DEMO = ec.point_value(5, 325, R_DISC)


def simulate(lending_ratio: float, n_build: int, v: float) -> dict:
    eco = Economy(fee=ec.keeper_fee(v, M), yield_rate=YIELD)
    eco.add_agent("world", reputation=1e9)
    for k in range(LENDERS):
        eco.add_agent(f"lender{k}", money=1e12)
    attacker = eco.add_agent("attacker", money=1e9, reputation=R0)
    eco.donate(v * R_DISC * eco.total_reputation / YIELD)
    start = attacker.money

    for _ in range(n_build):  # buy reputation: cheap loans, kept
        eco.repay_loan(eco.loan("attacker", "lender0", principal=1.0))
    reputation = attacker.reputation

    bond = reputation / LENDERS
    loans = [eco.loan("attacker", f"lender{k}", principal=lending_ratio * bond, bond=bond) for k in range(LENDERS)]
    for loan in loans:
        eco.default_loan(loan)

    scam_fees = LENDERS * eco.fee  # the fees on the loans that are defaulted on
    return dict(
        reputation_bonded=reputation, borrowed=lending_ratio * reputation,
        profit=attacker.money - start - v * R0, scam_fees=scam_fees,
        reputation_after=attacker.reputation, debts=attacker.debts,
    )


def main():
    rows = []
    for v in (V_DEMO, 1.0):
        for ratio_in_v in (0.5, 1.0, 1.25, 1.5, 2.0, 5.0, 20 / V_DEMO):
            for n in (0, 10, 40):
                ell = ratio_in_v * v
                sim = simulate(ell, n, v)
                formula = ec.exit_scam_profit(ell, v, R0, n, M)
                rows.append(dict(v=v, ratio_in_v=ratio_in_v, n_build=n, formula=formula,
                                 simulated_before_scam_fees=sim["profit"] + sim["scam_fees"], **sim))
    worst = max(abs(r["simulated_before_scam_fees"] - r["formula"]) / max(1.0, abs(r["formula"])) for r in rows)

    demo = dict(
        ell=20.0, v=V_DEMO, ratio_in_v=20 / V_DEMO,
        profit_100_points=ec.exit_scam_profit(20.0, V_DEMO, R0, 0, M),
        profit_per_extra_promise=ec.REP_GAIN * (20.0 - M * V_DEMO),
    )
    credit_line = 1000.0
    honest = dict(credit_line=credit_line, points_needed=credit_line / V_DEMO,
                  promises_needed=credit_line / V_DEMO / ec.REP_GAIN, fees_to_build=M * credit_line)

    out = dict(provenance=run_provenance(), rows=rows, worst_error=worst, demo=demo, honest_cost=honest)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    lines = ["# Exit scam: results", "",
             f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
             f"{len(rows)} grid points; worst disagreement between simulation and formula {worst:.2e} "
             "(the simulation also pays the fee on each of the four defaulted loans, which the formula leaves out; it is added back for this comparison).", "",
             f"## Profit (DMD) from a 100-point identity, v = {V_DEMO:.4f} (demo)", "",
             f"Before the fees on the four defaulted loans ({LENDERS * ec.keeper_fee(V_DEMO, M):.2f} DMD in total, the same in every cell). "
             "n is the number of promises kept beforehand to buy reputation.", "",
             "| lending ratio / v | n = 0 | n = 10 | n = 40 | more building |", "|---|---|---|---|---|"]
    for ratio in sorted({r["ratio_in_v"] for r in rows}):
        cells = [next(r["simulated_before_scam_fees"] for r in rows if r["v"] == V_DEMO and r["ratio_in_v"] == ratio and r["n_build"] == n) for n in (0, 10, 40)]
        tolerance = 1e-6 * max(1.0, abs(cells[0]))
        trend = "raises profit" if cells[2] > cells[0] + tolerance else ("lowers profit" if cells[2] < cells[0] - tolerance else "no effect")
        lines.append(f"| {ratio:.2f} | " + " | ".join(f"{c:+.2f}" for c in cells) + f" | {trend} |")
    lines += ["", "## The demo's lending ratio", "",
              f"- 1000 DMD against a 50-point bond is {demo['ell']:.0f} DMD per point, {demo['ratio_in_v']:.0f} times the value of a point",
              f"- a 100-point identity extracts {demo['profit_100_points']:.0f} DMD; each extra kept promise adds {demo['profit_per_extra_promise']:.0f} DMD",
              "", "## What safe lending costs an honest user (lending ratio = v)", "",
              f"- a {honest['credit_line']:.0f} DMD credit line needs {honest['points_needed']:.0f} points, i.e. {honest['promises_needed']:.0f} kept promises",
              f"- at the keeper's fee those cost {honest['fees_to_build']:.0f} DMD"]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
