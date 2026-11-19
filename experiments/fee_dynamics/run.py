"""
Claim under test: with the fee keeper running, the reputation earned by a kept promise is never worth
more than the fee paid for it. See README.md for the arms and predictions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from rain import economics as ec
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
HONEST_REP, HONEST_PROMISES, INITIAL_FEE = 10_000.0, 100, 0.1
SHOCK_CYCLE, FARMER_CAP, FARMER_CHUNK = 50, 1000, 10

ARMS = {
    "A1_baseline": dict(m=1.5, y=0.004, r=0.05, horizon=700, evaluate_to=300),
    "A2_runaway": dict(m=1.5, y=0.004, r=0.004, horizon=7000, evaluate_to=1000),
    "A3_control_no_margin": dict(m=0.0, y=0.004, r=0.05, horizon=700, evaluate_to=300),
    "A4_shock": dict(m=1.5, y=0.004, r=0.05, horizon=700, evaluate_to=300, shock=10),
    "A5_shock_farmers": dict(m=1.5, y=0.004, r=0.05, horizon=700, evaluate_to=300, shock=10, farmers=True),
}


def simulate(m, y, r, horizon, shock=None, farmers=False, **_):
    eco = Economy(fee=INITIAL_FEE, yield_rate=y)
    honest = eco.add_agent("honest", money=1e30, reputation=HONEST_REP)
    farmer = eco.add_agent("farmer", money=1e30)
    path = []
    for t in range(horizon):
        if shock and t == SHOCK_CYCLE:
            eco.donate((shock - 1) * eco.treasury)
        fee = eco.fee
        eco.kept_promises("honest", HONEST_PROMISES)
        farmed = 0
        if farmers:
            # The farmer sees the treasury as it is now; the keeper's fee is based on past dividends.
            while farmed < FARMER_CAP and eco.rep_gain * ec.point_value(y * eco.treasury, eco.total_reputation, r) > fee:
                eco.kept_promises("farmer", FARMER_CHUNK)
                farmed += FARMER_CHUNK
        before = (honest.dividends_received, farmer.dividends_received)
        total_rep = eco.total_reputation
        dividend = eco.pay_dividend()
        eco.update_fee(margin=m, r=r)
        path.append(dict(
            t=t, fee=fee, total_reputation=total_rep, treasury=eco.treasury,
            dividend_per_point=dividend / total_rep, farmed=farmed,
            honest_dividend=honest.dividends_received - before[0],
            farmer_dividend=farmer.dividends_received - before[1],
            farmer_reputation=farmer.reputation,
        ))
    return path


def value_of_a_promise(path, r, g=ec.REP_GAIN):
    """Discounted dividends collected by the g points earned in each cycle (paid at the end of each cycle)."""
    values = [0.0] * len(path)
    tail = path[-1]["dividend_per_point"] / r  # beyond the horizon: constant
    for t in range(len(path) - 1, -1, -1):
        tail = (path[t]["dividend_per_point"] + tail) / (1 + r)
        values[t] = g * tail
    return values


def loglog_slope(path, start, stop):
    xs = [math.log(p["total_reputation"]) for p in path[start:stop]]
    ys = [math.log(p["fee"]) for p in path[start:stop]]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def discounted(path, key, r, start):
    return sum(p[key] / (1 + r) ** (p["t"] - start + 1) for p in path[start:])


def analyse(name, cfg):
    path = simulate(**cfg)
    values = value_of_a_promise(path, cfg["r"])
    ratios = [(v / p["fee"] if p["fee"] > 0 else math.inf) for v, p in zip(values, path)]
    window = range(5, cfg["evaluate_to"])
    out = dict(
        c=ec.fee_feedback_exponent(cfg["m"], cfg["y"], cfg["r"]),
        max_value_over_fee=max(ratios[t] for t in window),
        min_value_over_fee=min(ratios[t] for t in window),
        value_over_fee_at={str(t): ratios[t] for t in (5, 20, 49, 50, 51, 52, 53, 100, cfg["evaluate_to"] - 1)},
        fee_at={str(t): path[t]["fee"] for t in (1, 5, 20, 50, 100, cfg["evaluate_to"] - 1)},
        point_value_at={str(t): values[t] / ec.REP_GAIN for t in (5, 50, 100, cfg["evaluate_to"] - 1)},
        cycles_where_farming_pays=[t for t in window if ratios[t] > 1][:20],
        n_cycles_where_farming_pays=sum(1 for t in window if ratios[t] > 1),
    )
    if cfg["m"] > 0:
        out["fee_exponent_fitted"] = loglog_slope(path, 20, cfg["evaluate_to"])
        out["fee_exponent_predicted"] = out["c"] - 1
    if cfg.get("farmers"):
        r, s = cfg["r"], SHOCK_CYCLE
        farmer_fees = sum(p["farmed"] * p["fee"] / (1 + r) ** (p["t"] - s) for p in path[s:])
        farmer_income = discounted(path, "farmer_dividend", r, s) + (
            path[-1]["farmer_reputation"] * path[-1]["dividend_per_point"] / r / (1 + r) ** (len(path) - s))
        out["farmer"] = dict(
            promises_by_cycle={str(p["t"]): p["farmed"] for p in path if p["farmed"]},
            fees_paid=farmer_fees, dividends_collected=farmer_income, profit=farmer_income - farmer_fees,
            final_share_of_reputation=path[-1]["farmer_reputation"] / path[-1]["total_reputation"],
        )
        out["honest_dividends_from_shock"] = discounted(path, "honest_dividend", r, s)
    elif cfg.get("shock"):
        out["honest_dividends_from_shock"] = discounted(path, "honest_dividend", cfg["r"], SHOCK_CYCLE)
    return out


def main():
    results = {name: analyse(name, cfg) for name, cfg in ARMS.items()}
    results["A5_shock_farmers"]["honest_gain_from_farming"] = (
        results["A5_shock_farmers"]["honest_dividends_from_shock"] - results["A4_shock"]["honest_dividends_from_shock"])
    out = dict(provenance=run_provenance(), arms=ARMS, results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    fmt = lambda x: "inf" if x == math.inf else f"{x:.3f}"
    lines = ["# Fee dynamics: results", "",
             f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
             "| arm | c | fee exponent (fitted / predicted) | max value/fee | min value/fee | cycles where farming pays |",
             "|---|---|---|---|---|---|"]
    for name, res in results.items():
        exponent = f"{res['fee_exponent_fitted']:.3f} / {res['fee_exponent_predicted']:.3f}" if "fee_exponent_fitted" in res else "n/a"
        lines.append(f"| {name} | {res['c']:.2f} | {exponent} | {fmt(res['max_value_over_fee'])} | {fmt(res['min_value_over_fee'])} | {res['n_cycles_where_farming_pays']} {res['cycles_where_farming_pays'][:6]} |")
    lines += ["", "## Value of a promise / fee paid, by cycle", "", "| arm | " + " | ".join(f"t={t}" for t in (5, 20, 49, 50, 51, 52, 53, 100)) + " |", "|---|" + "---|" * 8]
    for name, res in results.items():
        lines.append(f"| {name} | " + " | ".join(fmt(res["value_over_fee_at"][str(t)]) for t in (5, 20, 49, 50, 51, 52, 53, 100)) + " |")
    lines += ["", "## Fee (DMD per promise) and value of a point over time", "", "| arm | fee t=1 | t=5 | t=20 | t=50 | t=100 | last | point value t=5 | t=100 | last |", "|---|" + "---|" * 9]
    for name, res in results.items():
        fees, pv = list(res["fee_at"].values()), list(res["point_value_at"].values())
        lines.append(f"| {name} | " + " | ".join(f"{x:.4g}" for x in fees) + f" | {pv[0]:.4g} | {pv[2]:.4g} | {pv[3]:.4g} |")
    f = results["A5_shock_farmers"]["farmer"]
    lines += ["", "## A5: the farmer after the shock", "",
              f"- wash promises by cycle: {f['promises_by_cycle']}",
              f"- fees paid {f['fees_paid']:.1f} DMD, dividends collected (discounted to the shock) {f['dividends_collected']:.1f} DMD, profit {f['profit']:.1f} DMD",
              f"- farmer's final share of all reputation: {f['final_share_of_reputation']:.3f}",
              f"- change in honest holders' discounted dividends caused by the farming: {results['A5_shock_farmers']['honest_gain_from_farming']:+.1f} DMD "
              f"(from {results['A4_shock']['honest_dividends_from_shock']:.1f})"]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
