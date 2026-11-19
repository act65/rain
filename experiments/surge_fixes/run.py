"""
Claim under test: which of three rule changes keeps the value of a point below its cost through
a surge in activity (and at start-up). See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
KAPPA, DELTA, R = 0.04, 0.03, 0.05
BASE, SHOCK, HORIZON = 100, 300, 1500
STEADY = BASE / KAPPA / DELTA

ARMS = {
    "baseline": dict(),
    "fixed issuance": dict(issuance=BASE / KAPPA),
    "smoothed, rho 0.03": dict(smooth=0.03),
    "smoothed, rho 0.1": dict(smooth=0.1),
    "smoothed, rho 0.3": dict(smooth=0.3),
    "smoothed, rho 0.03, no genesis": dict(smooth=0.03, genesis=0.0),
    "vesting 3": dict(vesting=3),
    "vesting 10": dict(vesting=10),
    "vesting 33": dict(vesting=33),
}


def simulate(scenario, issuance=None, smooth=None, vesting=0, genesis=STEADY):
    # `genesis_rules` is the design in force when this experiment was run; the options layer the candidates on it.
    eco = Economy.genesis_rules(min_fee=1.0, fee_rate=0.0, point_price=KAPPA, decay_rate=DELTA,
                                reserve_release=smooth if smooth else 0.03, genesis_reputation=genesis,
                                issuance_per_cycle=issuance, smooth_payout=bool(smooth), vesting_cycles=vesting)
    eco.add_agent("honest", money=1e30)
    path = []
    for t in range(HORIZON):
        activity = BASE
        if t >= SHOCK and scenario == "x10":
            activity = 10 * BASE
        if t >= SHOCK and scenario == "/10":
            activity = BASE // 10
        if t == SHOCK and scenario == "grant":
            eco.grant(10 * BASE)
        eco.kept_promises("honest", activity)
        eco.run_oracle()  # so that points issued this cycle are counted below
        earning = sum(a.earning_reputation for a in eco.agents.values())
        dividend = eco.pay_dividend()
        cost = activity / issuance if issuance else KAPPA  # fees paid per point earned this cycle
        path.append(dict(d=dividend / earning if earning else 0.0, cost=cost))
    # value of a point earned in cycle t: it starts collecting `vesting` cycles later, decaying meanwhile
    tail = path[-1]["d"] / (R + DELTA)
    collected = [0.0] * HORIZON  # value from cycle t on of a point that is already earning
    for t in range(HORIZON - 1, -1, -1):
        tail = (path[t]["d"] + (1 - DELTA) * tail) / (1 + R)
        collected[t] = tail
    wait = ((1 - DELTA) / (1 + R)) ** vesting
    return [(collected[t + vesting] * wait if t + vesting < HORIZON else 0.0) / path[t]["cost"] for t in range(HORIZON - 40)]


def analyse(arm):
    out = {}
    v = simulate("steady", **arm)
    out["startup"] = dict(t0=v[0], t5=v[5], t20=v[20], t100=v[100], peak=max(v[:200]), cycles_above_one=sum(x > 1 for x in v[:200]))
    out["steady"] = v[1000]
    for scenario in ("x10", "/10", "grant"):
        v = simulate(scenario, **arm)
        window = v[SHOCK:SHOCK + 200]
        out[scenario] = dict(at_shock=window[0], peak=max(window), trough=min(window), cycles_above_one=sum(x > 1 for x in window))
    return out


def main():
    results = {name: analyse(arm) for name, arm in ARMS.items()}
    out = dict(provenance=run_provenance(), arms=ARMS, results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    L = ["# Damping a surge: results", "",
         f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
         "Value of a point / its cost. Farming pays above 1.", "",
         "| arm | steady | start-up: cycle 0 | cycle 5 | cycle 20 | peak | tenfold rise: at shock | peak | cycles above 1 | tenfold fall: trough | grant: peak |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        s = r["startup"]
        L.append(f"| {name} | {r['steady']:.3f} | {s['t0']:.3f} | {s['t5']:.3f} | {s['t20']:.3f} | {s['peak']:.3f} | "
                 f"{r['x10']['at_shock']:.3f} | {r['x10']['peak']:.3f} | {r['x10']['cycles_above_one']} | {r['/10']['trough']:.3f} | {r['grant']['peak']:.3f} |")
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
