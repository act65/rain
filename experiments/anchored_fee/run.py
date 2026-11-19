"""
Claim under test: with a fixed price per point and decay (and fees paid out), reputation has a stable
value below its cost, so farming never pays. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain import economics as ec
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
Y, R, M = 0.004, 0.05, 1.5
FEE, KAPPA = 1.0, 0.04
HONEST_REP, HONEST_PROMISES = 10_000.0, 100
SHOCK_CYCLE, FARMER_CAP, FARMER_CHUNK = 50, 1000, 10

ARMS = {
    "B0_keeper": dict(keeper=True, delta=0.0, horizon=700, evaluate_to=300),
    "B1": dict(delta=0.03, horizon=2500, evaluate_to=1000),
    "B2_pass_through": dict(delta=0.03, pass_through=True, horizon=2500, evaluate_to=1000),
    "B1s_slow_decay": dict(delta=0.005, horizon=6000, evaluate_to=3000),
    "B2s_slow_decay": dict(delta=0.005, pass_through=True, horizon=6000, evaluate_to=3000),
    "B1_shock": dict(delta=0.03, shock=True, horizon=2500, evaluate_to=300),
    "B2_shock": dict(delta=0.03, pass_through=True, shock=True, horizon=2500, evaluate_to=300),
    "B1_shock_farmer": dict(delta=0.03, shock=True, farmers=True, horizon=2500, evaluate_to=300),
    "B2_shock_farmer": dict(delta=0.03, pass_through=True, shock=True, farmers=True, horizon=2500, evaluate_to=300),
    # Start-up rule: nobody starts with reputation; the treasury holds a genesis reserve at the steady-state
    # supply, which decays away. Its share of each dividend is not paid out and rolls into the next cycle.
    "B3_genesis_reserve": dict(delta=0.03, pass_through=True, genesis=True, horizon=2500, evaluate_to=1000),
    "B3_genesis_reserve_farmer": dict(delta=0.03, pass_through=True, genesis=True, farmers=True, horizon=2500, evaluate_to=1000),
    "B3_half_sized_reserve": dict(delta=0.03, pass_through=True, genesis=0.5, horizon=2500, evaluate_to=1000),
    "B3_double_sized_reserve": dict(delta=0.03, pass_through=True, genesis=2.0, horizon=2500, evaluate_to=1000),
    # As B3, but the share kept back goes into a fund, of which a fraction `release` is paid out each cycle.
    "B4_fund_never_released": dict(delta=0.03, pass_through=True, genesis=True, release=0.0, horizon=2500, evaluate_to=1000),
    "B4_fund_released_slowly": dict(delta=0.03, pass_through=True, genesis=True, release=0.015, horizon=2500, evaluate_to=1000),
    "B4_fund_released_at_decay_rate": dict(delta=0.03, pass_through=True, genesis=True, release=0.03, horizon=2500, evaluate_to=1000),
    "B4_released_at_decay_rate_farmer": dict(delta=0.03, pass_through=True, genesis=True, release=0.03, farmers=True, horizon=2500, evaluate_to=1000),
    "B4_half_sized_reserve": dict(delta=0.03, pass_through=True, genesis=0.5, release=0.03, horizon=2500, evaluate_to=1000),
    "B4_half_sized_reserve_farmer": dict(delta=0.03, pass_through=True, genesis=0.5, release=0.03, farmers=True, horizon=2500, evaluate_to=1000),
    "B4_slow_decay": dict(delta=0.005, pass_through=True, genesis=True, release=0.005, horizon=6000, evaluate_to=3000),
}


def simulate(delta, horizon, keeper=False, pass_through=False, shock=False, farmers=False, genesis=False, release=None, **_):
    if keeper:
        eco = Economy(fee=0.1, yield_rate=Y)
    else:
        eco = Economy(fee=FEE, yield_rate=Y, point_price=KAPPA, decay_rate=delta, pass_through=pass_through)
    honest = eco.add_agent("honest", money=1e30, reputation=0.0 if genesis else HONEST_REP)
    if genesis:
        steady = HONEST_PROMISES * FEE / KAPPA / delta  # supply before decay, once issuance equals decay
        eco.add_agent("reserve", reputation=float(genesis) * steady)
        eco.reserve_holder = "reserve"
        eco.reserve_release = release
    farmer = eco.add_agent("farmer", money=1e30)
    path = []
    for t in range(horizon):
        if shock and t == SHOCK_CYCLE:
            if pass_through:
                eco.grant(10 * HONEST_PROMISES * FEE)
            else:
                eco.donate(9 * eco.treasury)
        cost_per_point = eco.fee / eco.reward()
        eco.kept_promises("honest", HONEST_PROMISES)
        farmed = 0
        if farmers:
            def expected_value_of_a_point():
                # This cycle's dividend (including any grant waiting to be paid), then the usual one for ever.
                total = eco.total_reputation
                released = (eco.reserve_release or 0.0) * eco.reserve_fund
                this_cycle = (Y * eco.treasury + eco.fee_pool + released) / total
                # Money held back for the reserve is on its way out to holders, so "usual" is at least this cycle's pool.
                usual = (Y * eco.treasury + released + (max(HONEST_PROMISES * FEE, eco.fee_pool if genesis else 0.0) if pass_through else 0.0)) / total
                return this_cycle / (1 + R) + (1 - delta) / (1 + R) * ec.decaying_point_value(usual, R, delta)
            while farmed < FARMER_CAP and expected_value_of_a_point() > cost_per_point:
                eco.kept_promises("farmer", FARMER_CHUNK)
                farmed += FARMER_CHUNK
        total_rep = eco.total_reputation
        before = farmer.dividends_received
        dividend = eco.pay_dividend()
        if keeper:
            eco.update_fee(margin=M, r=R)
        path.append(dict(t=t, cost_per_point=cost_per_point, total_reputation=total_rep, supply_after_decay=eco.total_reputation,
                         dividend_per_point=dividend / total_rep, treasury=eco.treasury, farmed=farmed,
                         farmer_fees=farmed * FEE, farmer_dividend=farmer.dividends_received - before))
    return path


def value_of_a_point(path, delta):
    """Discounted dividends collected by one point bought in each cycle, shrinking by delta per cycle."""
    values = [0.0] * len(path)
    tail = path[-1]["dividend_per_point"] / (R + delta)  # beyond the horizon: constant
    for t in range(len(path) - 1, -1, -1):
        tail = (path[t]["dividend_per_point"] + (1 - delta) * tail) / (1 + R)
        values[t] = tail
    return values


def analyse(cfg):
    path = simulate(**cfg)
    delta = cfg["delta"]
    ratios = [v / p["cost_per_point"] for v, p in zip(value_of_a_point(path, delta), path)]
    window = range(0, cfg["evaluate_to"])
    marks = [t for t in (0, 5, 20, 49, 50, 51, 100, 200, 650, 1000, 2999) if t < cfg["evaluate_to"]]
    first_cross = next((t for t in window if ratios[t] > 1), None)
    out = dict(
        value_over_cost_at={str(t): ratios[t] for t in marks},
        max_value_over_cost=max(ratios[t] for t in window),
        first_cycle_farming_pays=first_cross,
        n_cycles_farming_pays=sum(1 for t in window if ratios[t] > 1),
        supply_at={str(t): path[t]["supply_after_decay"] for t in marks},
        cost_per_point_at={str(t): path[t]["cost_per_point"] for t in marks},
        value_of_a_point_at={str(t): ratios[t] * path[t]["cost_per_point"] for t in marks},
    )
    if not cfg.get("keeper"):
        out["steady_supply_predicted"] = ec.steady_state_supply(HONEST_PROMISES * FEE, KAPPA, delta)
        out["steady_value_over_cost_predicted_pass_through"] = ec.pass_through_value_over_cost(R, delta)
    if cfg.get("farmers"):
        # Discounted to cycle 0, over the whole run (the farmer may act long before or after the shock).
        fees = sum(p["farmer_fees"] / (1 + R) ** p["t"] for p in path)
        income = sum(p["farmer_dividend"] / (1 + R) ** (p["t"] + 1) for p in path)
        active = [p["t"] for p in path if p["farmed"]]
        out["farmer"] = dict(total_promises=sum(p["farmed"] for p in path), first_cycle=min(active) if active else None,
                             last_cycle=max(active) if active else None, promises_in_shock_cycle=path[SHOCK_CYCLE]["farmed"],
                             fees_paid=fees, dividends_collected=income, profit=income - fees)
    return out


def main():
    results = {name: analyse(cfg) for name, cfg in ARMS.items()}
    out = dict(provenance=run_provenance(), arms=ARMS, results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    def cells(d, marks, fmt):
        return " | ".join(fmt(d[str(t)]) if str(t) in d else "" for t in marks)

    marks = (0, 5, 20, 49, 50, 51, 100, 200, 650, 1000, 2999)
    lines = ["# Anchored fee: results", "",
             f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
             "## Value of a point / what it cost, by cycle (farming pays above 1)", "",
             "| arm | " + " | ".join(f"t={t}" for t in marks) + " | max | first cycle above 1 |", "|---|" + "---|" * (len(marks) + 2)]
    for name, res in results.items():
        lines.append(f"| {name} | {cells(res['value_over_cost_at'], marks, lambda x: f'{x:.3f}')} | {res['max_value_over_cost']:.3f} | {res['first_cycle_farming_pays']} |")
    lines += ["", "## Total reputation (after decay)", "", "| arm | " + " | ".join(f"t={t}" for t in marks) + " | predicted steady state |", "|---|" + "---|" * (len(marks) + 1)]
    for name, res in results.items():
        lines.append(f"| {name} | {cells(res['supply_at'], marks, lambda x: f'{x:,.0f}')} | {res.get('steady_supply_predicted', float('nan')):,.0f} |")
    lines += ["", "## Value of one point (DMD)", "", "| arm | " + " | ".join(f"t={t}" for t in marks) + " |", "|---|" + "---|" * len(marks)]
    for name, res in results.items():
        lines.append(f"| {name} | {cells(res['value_of_a_point_at'], marks, lambda x: f'{x:.3g}')} |")
    lines += ["", "## Farmers", ""]
    for name in ("B1_shock_farmer", "B2_shock_farmer", "B3_genesis_reserve_farmer", "B4_released_at_decay_rate_farmer", "B4_half_sized_reserve_farmer"):
        f = results[name]["farmer"]
        if not f["total_promises"]:
            lines.append(f"- {name}: no wash promises at any cycle")
            continue
        lines.append(f"- {name}: {f['total_promises']} wash promises between cycles {f['first_cycle']} and {f['last_cycle']} "
                     f"({f['promises_in_shock_cycle']} in the shock cycle); discounted to cycle 0: fees {f['fees_paid']:.1f}, "
                     f"dividends {f['dividends_collected']:.1f}, profit {f['profit']:+.1f} DMD")
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
