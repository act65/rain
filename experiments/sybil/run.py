"""
Claim under test: a disposable identity is profitable exactly when lenders advance more per point than
the point cost to obtain (nothing if minted free, `m * v` if bought, `v` of a sponsor's if vouched).
See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain import economics as ec
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
M, R_DISC, YIELD = 1.5, 0.05, 0.004
POINTS = 100.0
V = ec.point_value(5, 325, R_DISC)
LENDERS = {"naive (20 per point)": 20.0, "careful (0.9 v per point)": 0.9 * V}


def world(v: float) -> Economy:
    eco = Economy(fee=ec.keeper_fee(v, M), yield_rate=YIELD)
    eco.add_agent("world", reputation=1e9)
    eco.add_agent("lender", money=1e12)
    eco.donate(v * R_DISC * eco.total_reputation / YIELD)
    return eco


def s1_free_mint(ell: float) -> dict:
    eco = world(V)
    sybil = eco.add_agent("sybil", money=1e6, reputation=POINTS)  # minted free
    start = sybil.money
    eco.default_loan(eco.loan("sybil", "lender", principal=ell * POINTS, bond=POINTS))
    return dict(profit=sybil.money - start, formula=ell * POINTS - eco.fee, hold_instead=V * POINTS)


def s2_bought(ell: float) -> dict:
    eco = world(V)
    sybil = eco.add_agent("sybil", money=1e6)
    eco.add_agent("partner", money=1e6)
    start = sybil.money
    for _ in range(int(POINTS / eco.rep_gain)):  # wash promises with the partner
        eco.repay_loan(eco.loan("sybil", "partner", principal=1.0))
    eco.default_loan(eco.loan("sybil", "lender", principal=ell * POINTS, bond=POINTS))
    return dict(profit=sybil.money - start, formula=POINTS * (ell - M * V) - eco.fee)


def s3_vouched(ell: float) -> dict:
    eco = world(V)
    sponsor = eco.add_agent("sponsor", money=1e6, reputation=1000.0)  # an established identity the attacker owns
    recruit = eco.add_agent("recruit", money=1e6)
    start = sponsor.money + recruit.money
    eco.stake("sponsor", POINTS)  # the vouching bond
    loan = eco.loan("recruit", "lender", principal=ell * POINTS)  # lent against the sponsor's bond
    eco.default_loan(loan)
    burned = eco.forfeit_stake("sponsor", POINTS)
    profit = sponsor.money + recruit.money - start - V * burned  # the sponsor's lost dividends count
    return dict(profit=profit, formula=POINTS * (ell - V) - eco.fee, sponsor_reputation_lost=burned)


def scaling(n_identities: int, lender: str) -> dict:
    """N bought identities attack in one cycle of a running economy; compare with no attack."""
    def run(attack: bool):
        eco = Economy(fee=0.1, yield_rate=YIELD)
        honest = eco.add_agent("honest", money=1e30, reputation=10_000.0)
        eco.add_agent("lender", money=1e30)
        eco.add_agent("partner", money=1e30)
        for _ in range(50):
            eco.kept_promises("honest", 100)
            eco.pay_dividend()
            eco.update_fee(M, R_DISC)
        info = dict(fee=eco.fee, v_before=eco.point_value(R_DISC))
        eco.kept_promises("honest", 100)
        if attack:
            sybils = eco.add_agent("sybils", money=1e30)  # N identities, pooled
            washes = int(POINTS / eco.rep_gain) * n_identities
            eco.kept_promises("sybils", washes)
            info["dilution_at_peak"] = sybils.reputation / eco.total_reputation
            if lender == "naive":
                ell = 20.0
            else:  # lends against the value of a point as it stands now, after the dilution
                ell = 0.9 * ec.point_value(YIELD * eco.treasury, eco.total_reputation, R_DISC)
            # One loan per identity, each bonding its 100 points. The identities are pooled into one
            # agent, and a default would bar the whole pool, so every loan is taken before any defaults.
            loans = []
            for _ in range(n_identities):
                loans.append(eco.loan("sybils", "lender", principal=ell * POINTS, bond=POINTS))
            for loan in loans:
                eco.default_loan(loan)
            # Flows are summed directly: differences of the agents' (huge) balances would lose them to rounding.
            borrowed = sum(eco.loans[loan].principal for loan in loans)
            info.update(profit=borrowed - sybils.fees_paid, lender_loss=borrowed, fees_paid=sybils.fees_paid,
                        sybil_reputation_after=sybils.reputation, lending_ratio=ell)
        before = honest.dividends_received
        eco.pay_dividend()
        info["honest_dividend_per_point_next_cycle"] = (honest.dividends_received - before) / honest.reputation
        return info

    attacked, quiet = run(True), run(False)
    attacked["profit_per_identity"] = attacked["profit"] / n_identities
    attacked["honest_dividend_change"] = (
        attacked["honest_dividend_per_point_next_cycle"] / quiet["honest_dividend_per_point_next_cycle"] - 1)
    return attacked


def main():
    scenarios = {}
    for label, ell in LENDERS.items():
        scenarios[label] = dict(S1_free_mint=s1_free_mint(ell), S2_bought=s2_bought(ell), S3_vouched=s3_vouched(ell))
    scale = {lender: {str(n): scaling(n, lender) for n in (1, 10, 100, 1000)} for lender in ("naive", "careful")}

    out = dict(provenance=run_provenance(), v=V, scenarios=scenarios, scaling=scale)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    lines = ["# Sybil identities: results", "",
             f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
             f"## Profit per 100-point identity (DMD), v = {V:.4f}", "",
             "| scenario | " + " | ".join(f"{label}: simulated (formula)" for label in LENDERS) + " |", "|---|---|---|"]
    for name in ("S1_free_mint", "S2_bought", "S3_vouched"):
        lines.append(f"| {name} | " + " | ".join(f"{scenarios[l][name]['profit']:+.2f} ({scenarios[l][name]['formula']:+.2f})" for l in LENDERS) + " |")
    lines += ["", f"Holding a free-minted identity instead of attacking with it is worth {V * POINTS:.2f} DMD in dividends.", "",
              "## Scaling: N bought identities attacking a running economy in one cycle", "",
              "| lender | N | fee per promise | cost of 100 points | lent per point | profit per identity | lenders' loss | sybil share of reputation at peak | honest dividend per point, next cycle |",
              "|---|---|---|---|---|---|---|---|---|"]
    for lender, by_n in scale.items():
        for n, r in by_n.items():
            lines.append(f"| {lender} | {n} | {r['fee']:.2e} | {4 * r['fee']:.2e} | {r['lending_ratio']:.3g} | {r['profit_per_identity']:+.4g} | {r['lender_loss']:.4g} | {r['dilution_at_peak']:.3f} | {r['honest_dividend_change']:+.2%} |")
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
