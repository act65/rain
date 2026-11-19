"""
Claim under test: a lag between a promise being resolved and the oracle's update costs newcomers a
delay, does not affect established honest agents, and does not benefit defaulters. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
KAPPA, DELTA, R, RELEASE = 0.04, 0.03, 0.05, 0.03
HONEST, DEFAULTERS, EVERY, DELINQUENT_FOR, BOND_FRACTION = 100, 10, 20, 3, 0.2
JOIN, START, END = 300, 300, 700
LAGS = [0, 1, 3, 6, 12]


def simulate(lag):
    eco = Economy.current_rules(min_fee=1.0, fee_rate=0.0, point_price=KAPPA, decay_rate=DELTA, oracle_lag=lag)
    eco.add_agent("bank", money=1e30)
    honest = [f"h{i}" for i in range(HONEST)]
    defaulters = [f"d{i}" for i in range(DEFAULTERS)]
    for name in honest + defaulters + ["newcomer"]:
        eco.add_agent(name, money=1e12)
    settle_at, loans_taken = {}, {name: 0 for name in defaulters}
    series = {"honest": [], "defaulters": [], "newcomer": []}

    for t in range(END):
        for name in honest + (["newcomer"] if t >= JOIN else []):
            eco.repay_loan(eco.loan(name, "bank", principal=1.0))
        for k, name in enumerate(defaulters):
            if name in settle_at:
                when, loan = settle_at[name]
                if t < when:
                    continue
                eco.resolve_default(loan)
                del settle_at[name]
            loan = eco.loan(name, "bank", principal=1.0, bond=BOND_FRACTION * eco.agents[name].liquid_reputation)
            loans_taken[name] += 1
            if (loans_taken[name] + 2 * k) % EVERY == 0:  # staggered across defaulters
                eco.default_loan(loan)
                settle_at[name] = (t + DELINQUENT_FOR, loan)
            else:
                eco.repay_loan(loan)
        before = {g: sum(eco.agents[n].dividends_received for n in names)
                  for g, names in (("honest", honest), ("defaulters", defaulters), ("newcomer", ["newcomer"]))}
        eco.pay_dividend()
        for g, names in (("honest", honest), ("defaulters", defaulters), ("newcomer", ["newcomer"])):
            series[g].append(sum(eco.agents[n].dividends_received for n in names) - before[g])

    window = slice(START, END)
    return dict(
        honest_dividends=sum(series["honest"][window]) / HONEST,
        defaulter_dividends=sum(series["defaulters"][window]) / DEFAULTERS,
        newcomer_present_value=sum(d / (1 + R) ** (t - JOIN + 1) for t, d in enumerate(series["newcomer"]) if t >= JOIN),
        honest_reputation=sum(eco.agents[n].reputation for n in honest) / HONEST,
        defaulter_reputation=sum(eco.agents[n].reputation for n in defaulters) / DEFAULTERS,
    )


def main():
    results = {str(lag): simulate(lag) for lag in LAGS}
    base = results["0"]
    for lag, r in results.items():
        r["honest_relative"] = r["honest_dividends"] / base["honest_dividends"]
        r["defaulter_relative"] = r["defaulter_dividends"] / base["defaulter_dividends"]
        r["newcomer_relative"] = r["newcomer_present_value"] / base["newcomer_present_value"]
        r["newcomer_predicted"] = (1 + R) ** -int(lag)
    out = dict(provenance=run_provenance(), results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    L = ["# Oracle lag: results", "",
         f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
         "Dividends over cycles 300 to 700, relative to no lag.", "",
         "| lag (cycles) | honest agent | defaulter | newcomer's present value | predicted for the newcomer | defaulter's reputation at the end | honest agent's |",
         "|---|---|---|---|---|---|---|"]
    L += [f"| {lag} | {r['honest_relative']:.4f} | {r['defaulter_relative']:.4f} | {r['newcomer_relative']:.4f} | {r['newcomer_predicted']:.4f} | {r['defaulter_reputation']:.1f} | {r['honest_reputation']:.1f} |"
          for lag, r in results.items()]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
