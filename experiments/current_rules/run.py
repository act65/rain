"""
Claims under test: the questions of the first four experiments, re-asked of the current rules.
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
KAPPA, DELTA, R, PHI, FMIN, INTEREST, RELEASE = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05, 0.03
RULES = dict(point_price=KAPPA, r=R, decay_rate=DELTA, fee_rate=PHI, min_fee=FMIN)
V = ec.current_point_value(KAPPA, R, DELTA)


def steady_world(point_price=KAPPA, fee_flow=1e6):
    """An economy at its steady state, large enough that one more agent does not move the dividend per point."""
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=point_price or 1.0, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=fee_flow / (point_price or 1.0) / DELTA)
    if point_price:
        eco.start_in_steady_state(fee_flow)

    def tick():
        eco.pay_dividend()
        if point_price:
            eco.kept_promises("world", amount=fee_flow / PHI)  # one promise carrying the world's fees for the cycle
    return eco, tick


# --- A. the frontier ---

def present_value(strategy, principal, reputation, bond, sigma, point_price=KAPPA, horizon=400):
    eco, tick = steady_world(point_price)
    eco.add_agent("lender", money=1e30)
    borrower = eco.add_agent("borrower", money=1e6, reputation=reputation)  # small, so that differences in it keep their precision
    interest = INTEREST * principal

    loan = eco.loan("borrower", "lender", principal, interest, bond)  # sunk: already funded
    before = borrower.money
    eco.default_loan(loan) if strategy == "default" else eco.repay_loan(loan)
    pv = borrower.money - before
    for t in range(1, horizon + 1):
        before = borrower.money
        tick()
        if strategy == "continue":
            loan = eco.loan("borrower", "lender", principal, interest, min(bond, borrower.liquid_reputation))
            borrower.money += (sigma + INTEREST) * principal
            eco.repay_loan(loan)
        pv += (borrower.money - before) / (1 + R) ** t
    return pv


def simulated_gain(principal, reputation, bond, sigma, point_price=KAPPA):
    honest = max(present_value(s, principal, reputation, bond, sigma, point_price) for s in ("continue", "stop"))
    return present_value("default", principal, reputation, bond, sigma, point_price) - honest


def simulated_max_safe_loan(reputation, bond, sigma):
    lo, hi = 0.0, 1.0
    while simulated_gain(hi, reputation, bond, sigma) <= 0:
        hi *= 2
    for _ in range(45):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if simulated_gain(mid, reputation, bond, sigma) > 0 else (mid, hi)
    return (lo + hi) / 2


def part_a():
    rows = []
    for reputation, bond_fraction, sigma in itertools.product([500, 5000], [0.2, 1.0], [0.0, 0.005, 0.02, 0.045]):
        bond = bond_fraction * reputation
        formula = ec.current_max_safe_loan(INTEREST, reputation, bond, surplus_rate=sigma, **RULES)
        simulated = simulated_max_safe_loan(reputation, bond, sigma)
        rows.append(dict(reputation=reputation, bond=bond, sigma=sigma, formula=formula, simulated=simulated,
                         relative_error=abs(simulated - formula) / formula, per_point_in_v=formula / reputation / V))
    demo = ec.current_max_safe_loan(INTEREST * 110 / 110 * 5 / 5.5, 26.25, 20, **RULES)  # 5 DMD interest on 110
    demo = ec.current_max_safe_loan(5 / 110, 26.25, 20, **RULES)
    return dict(
        rows=rows, v=V, fees_per_unit_of_credit=KAPPA / V, repaid_volume_per_unit_of_credit=KAPPA / V / PHI,
        surplus_threshold=PHI * (1 + INTEREST) * R / (R + DELTA),
        demo_safe_loan=demo, demo_loan=110, demo_oversize=110 / demo,
        control={str(p): simulated_gain(p, 1000, 1000, 0.0, point_price=0.0) for p in (1, 100)},
    )


# --- B. activity shocks ---

def activity_shock(multiplier, farmers=False, start=300, horizon=1500, evaluate=200, cap=1000, base=100):
    eco = Economy.current_rules(min_fee=1.0, fee_rate=0.0, point_price=KAPPA, decay_rate=DELTA)
    honest = eco.add_agent("honest", money=1e30)
    farmer = eco.add_agent("farmer", money=1e30)
    path = []
    for t in range(horizon):
        activity = int(base * multiplier) if t >= start else base
        eco.kept_promises("honest", activity)
        farmed = 0
        if farmers and t >= start:
            def expected_value():
                total = eco.total_reputation
                # The fund pays out a fraction of itself; take the dividend to stay at this cycle's level.
                this_cycle = RELEASE * (eco.fee_pool + eco.reserve_fund) / total
                return ec.decaying_point_value(this_cycle, R, DELTA)
            while farmed < cap and expected_value() > KAPPA:
                eco.kept_promises("farmer", 10)
                farmed += 10
        total = eco.total_reputation
        before = (honest.dividends_received, farmer.dividends_received)
        dividend = eco.pay_dividend()
        path.append(dict(t=t, d=dividend / total, supply=total, farmed=farmed,
                         honest_div=honest.dividends_received - before[0], farmer_div=farmer.dividends_received - before[1]))
    values = [0.0] * horizon
    tail = path[-1]["d"] / (R + DELTA)
    for t in range(horizon - 1, -1, -1):
        tail = (path[t]["d"] + (1 - DELTA) * tail) / (1 + R)
        values[t] = tail / KAPPA
    window = range(start, start + evaluate)
    out = dict(
        before=values[start - 1], at_shock=values[start], peak=max(values[t] for t in window), trough=min(values[t] for t in window),
        cycles_above_one=sum(1 for t in window if values[t] > 1), after_100=values[start + 100],
        honest_dividends=sum(p["honest_div"] / (1 + R) ** (p["t"] - start + 1) for p in path[start:]),
    )
    if farmers:
        fees = sum(p["farmed"] / (1 + R) ** (p["t"] - start) for p in path[start:])
        income = sum(p["farmer_div"] / (1 + R) ** (p["t"] - start + 1) for p in path[start:])
        active = [p["t"] - start for p in path if p["farmed"]]
        out["farmer"] = dict(promises=sum(p["farmed"] for p in path), first=min(active) if active else None,
                             last=max(active) if active else None, fees=fees, dividends=income, profit=income - fees)
    return out


def part_b():
    out = {"x2": activity_shock(2), "x10": activity_shock(10), "/10": activity_shock(0.1), "x10 + farmer": activity_shock(10, farmers=True)}
    out["x10 + farmer"]["honest_change"] = out["x10 + farmer"]["honest_dividends"] / out["x10"]["honest_dividends"] - 1
    return out


# --- C. exit scam ---

def scam(lending_ratio, bought):
    eco, _ = steady_world()
    for k in range(4):
        eco.add_agent(f"lender{k}", money=1e30)
    eco.add_agent("partner", money=1e30)
    attacker = eco.add_agent("attacker", money=1e9, reputation=100.0)
    start = attacker.money
    if bought:  # one wash loan with a partner, sized so that its fee buys the points
        eco.repay_loan(eco.loan("attacker", "partner", principal=bought * KAPPA / PHI))
    bond = attacker.reputation / 4
    loans = [eco.loan("attacker", f"lender{k}", principal=lending_ratio * bond, bond=bond) for k in range(4)]
    scam_fees = sum(eco.loans[l].fee_paid for l in loans)
    for l in loans:
        eco.default_loan(l)
    return attacker.money - start - V * 100.0 + scam_fees, scam_fees, attacker.reputation


def part_c():
    rows = []
    demo_ratio = 110 / 20
    for ratio_in_v, bought in itertools.product([0.5, 1.0, 2.0, KAPPA / V, 4.0, demo_ratio / V], [0, 250, 1000]):
        sim, fees, left = scam(ratio_in_v * V, bought)
        formula = ec.current_exit_scam_profit(ratio_in_v * V, KAPPA, R, DELTA, 100.0, bought)
        rows.append(dict(ratio_in_v=ratio_in_v, bought=bought, simulated=sim, formula=formula, scam_fees=fees, reputation_left=left))
    worst = max(abs(r["simulated"] - r["formula"]) / max(1.0, abs(r["formula"])) for r in rows)
    return dict(rows=rows, worst_error=worst, demo_ratio=demo_ratio, demo_ratio_in_v=demo_ratio / V)


# --- D. identities ---

def identity(kind, lending_ratio):
    eco, _ = steady_world()
    eco.add_agent("lender", money=1e30)
    eco.add_agent("partner", money=1e30)
    sybil = eco.add_agent("sybil", money=1e6)
    sponsor = eco.add_agent("sponsor", money=1e6, reputation=1000.0)
    start = sybil.money + sponsor.money
    cost = 0.0
    if kind == "bought":
        eco.repay_loan(eco.loan("sybil", "partner", principal=100 * KAPPA / PHI))
    if kind == "vouched":
        eco.stake("sponsor", 100.0)
    bonded = sybil.reputation if kind != "vouched" else 100.0
    loan = eco.loan("sybil", "lender", principal=lending_ratio * bonded, bond=sybil.reputation if kind != "vouched" else 0.0)
    eco.default_loan(loan)
    if kind == "vouched":
        cost = V * eco.forfeit_stake("sponsor", 100.0)
    profit = sybil.money + sponsor.money - start - cost
    per_point = {"none": 0.0, "bought": KAPPA, "vouched": V}[kind]
    formula = (bonded * (lending_ratio - per_point) if kind != "none" else 0.0) - eco.loans[loan].fee_paid
    return dict(profit=profit, formula=formula, borrowed=lending_ratio * bonded)


def scaling(n, lending_ratio=5.5, base=100):
    def run(attack):
        eco = Economy.current_rules(min_fee=1.0, fee_rate=0.0, point_price=KAPPA, decay_rate=DELTA)
        honest = eco.add_agent("honest", money=1e30)
        eco.add_agent("lender", money=1e30)
        for _ in range(300):
            eco.kept_promises("honest", base)
            eco.pay_dividend()
        eco.kept_promises("honest", base)
        info = {}
        if attack:
            sybils = eco.add_agent("sybils", money=1e30)
            eco.kept_promises("sybils", 4 * n)  # 100 points each, at 25 points per 1 DMD fee
            share = sybils.reputation / eco.total_reputation
            loans = [eco.loan("sybils", "lender", principal=lending_ratio * 100, bond=100) for _ in range(n)]
            for l in loans:
                eco.default_loan(l)
            borrowed = sum(eco.loans[l].principal for l in loans)
            info = dict(profit_per_identity=(borrowed - sybils.fees_paid) / n, lender_loss=borrowed, share_at_peak=share)
        before = honest.dividends_received
        eco.pay_dividend()
        info["honest_dividend_per_point"] = (honest.dividends_received - before) / honest.reputation * (1 - DELTA)
        return info
    attacked, quiet = run(True), run(False)
    attacked["honest_change"] = attacked["honest_dividend_per_point"] / quiet["honest_dividend_per_point"] - 1
    return attacked


def part_d():
    lenders = {"careful (0.9 v)": 0.9 * V, "demo ratio (5.5)": 5.5}
    return dict(
        scenarios={label: {kind: identity(kind, ell) for kind in ("none", "bought", "vouched")} for label, ell in lenders.items()},
        scaling={str(n): scaling(n) for n in (1, 10, 100, 1000)},
    )


def main():
    a, b, c, d = part_a(), part_b(), part_c(), part_d()
    out = dict(provenance=run_provenance(), rules=dict(RULES, release=RELEASE, interest=INTEREST), A=a, B=b, C=c, D=d)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    L = ["# The first four experiments under the current rules: results", "",
         f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
         f"A point is worth v = {V:.4f} DMD and costs {KAPPA} DMD.", "", "## A. Largest safe loan", "",
         f"Worst relative error, formula against simulation, over {len(a['rows'])} grid points: {max(r['relative_error'] for r in a['rows']):.1e}.", "",
         "| R | bond | sigma | P* formula | P* simulated | P* per point, in units of v |", "|---|---|---|---|---|---|"]
    L += [f"| {r['reputation']} | {r['bond']:.0f} | {r['sigma']} | {r['formula']:.3f} | {r['simulated']:.3f} | {r['per_point_in_v']:.3f} |" for r in a["rows"]]
    L += ["", f"- fees needed per unit of credit backed by a bond alone: {a['fees_per_unit_of_credit']:.2f} (i.e. {a['repaid_volume_per_unit_of_credit']:.0f} units of repaid loans at a 1% fee)",
          f"- surplus per loan above which access to future credit counts: {a['surplus_threshold']:.4%} of the principal",
          f"- the demo's second loan is {a['demo_loan']} DMD; the largest safe loan for that borrower is {a['demo_safe_loan']:.3f} DMD ({a['demo_oversize']:.0f} times smaller)",
          f"- control (worthless reputation): gain from defaulting {', '.join(f'P={p}: {g:+.2f}' for p, g in a['control'].items())}",
          "", "## B. A lasting change in activity at cycle 300 (value of a point / its cost)", "",
          "| arm | before | at the shock | peak | trough | 100 cycles later | cycles above 1 |", "|---|---|---|---|---|---|---|"]
    L += [f"| {name} | {r['before']:.3f} | {r['at_shock']:.3f} | {r['peak']:.3f} | {r['trough']:.3f} | {r['after_100']:.3f} | {r['cycles_above_one']} |" for name, r in b.items()]
    f = b["x10 + farmer"]["farmer"]
    L += ["", f"Farmer after the tenfold rise: {f['promises']} wash promises in cycles {f['first']} to {f['last']} after the shock; "
          f"fees {f['fees']:.0f}, dividends {f['dividends']:.0f}, profit {f['profit']:+.0f} DMD. "
          f"Honest holders' discounted dividends change by {b['x10 + farmer']['honest_change']:+.1%}.",
          "", "## C. Exit scam: profit from 100 existing points plus points bought (DMD, before the fees on the defaulted loans)", "",
          f"Worst disagreement between simulation and formula: {c['worst_error']:.1e}.", "",
          "| lending ratio / v | bought 0 | bought 250 | bought 1000 |", "|---|---|---|---|"]
    for ratio in sorted({r["ratio_in_v"] for r in c["rows"]}):
        cells = [next(r["simulated"] for r in c["rows"] if r["ratio_in_v"] == ratio and r["bought"] == n) for n in (0, 250, 1000)]
        L.append(f"| {ratio:.2f} | " + " | ".join(f"{x:+.2f}" for x in cells) + " |")
    L += ["", f"The demo lends {c['demo_ratio']} DMD per bonded point: {c['demo_ratio_in_v']:.0f} times v.",
          "", "## D. Profit per identity (DMD): simulated (formula)", "", "| identity | " + " | ".join(d["scenarios"]) + " |", "|---|---|---|"]
    for kind in ("none", "bought", "vouched"):
        L.append(f"| {kind} | " + " | ".join(f"{s[kind]['profit']:+.3f} ({s[kind]['formula']:+.3f})" for s in d["scenarios"].values()) + " |")
    L += ["", "| N bought identities | profit per identity | lenders' loss | sybil share of reputation at peak | honest dividend per point, next cycle |", "|---|---|---|---|---|"]
    L += [f"| {n} | {r['profit_per_identity']:+.1f} | {r['lender_loss']:,.0f} | {r['share_at_peak']:.3f} | {r['honest_change']:+.1%} |" for n, r in d["scaling"].items()]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
