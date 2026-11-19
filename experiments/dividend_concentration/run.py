"""
Claim under test: with decay, an agent's share of reputation tracks their share of activity and their
behaviour, not how early they arrived. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
KAPPA, PHI, FMIN, RELEASE = 0.04, 0.01, 0.1, 0.03
AGENTS, HORIZON, LAST_JOIN = 200, 800, 300
P_UNRELIABLE, P_DEFAULT, DELINQUENT_FOR, BOND_FRACTION = 0.2, 0.1, 5, 0.2
SEEDS = [0, 1, 2, 3, 4]
DECAYS = [0.03, 0.005, 0.0]
CHECKPOINTS = (400, 800)


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum()))


def population(seed):
    rng = np.random.default_rng(seed)
    activity = rng.lognormal(0.0, 1.0, AGENTS)
    join = np.where(np.arange(AGENTS) < AGENTS // 2, 0, rng.integers(1, LAST_JOIN + 1, AGENTS))
    unreliable = rng.random(AGENTS) < P_UNRELIABLE
    return activity, join, unreliable


def simulate(seed, decay):
    activity, join, unreliable = population(seed)
    rng = np.random.default_rng(1000 + seed)  # default draws: the same sequence in every arm
    fees = np.maximum(FMIN, PHI * 100 * activity)
    # The payout fund releases at the decay rate; with no decay that would be never, so that arm uses RELEASE.
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=decay,
                                release=decay if decay else RELEASE)
    eco.add_agent("bank", money=1e30)
    names = [f"a{i}" for i in range(AGENTS)]
    for name in names:
        eco.add_agent(name, money=1e12)
    settle_at = {}  # agent index -> (cycle, loan id)
    dividends = np.zeros((HORIZON, AGENTS))
    fees_paid = np.zeros((HORIZON, AGENTS))
    snapshots = {}

    for t in range(HORIZON):
        draws = rng.random(AGENTS)
        for i, name in enumerate(names):
            if t < join[i]:
                continue
            agent = eco.agents[name]
            if i in settle_at:
                when, loan = settle_at[i]
                if t < when:
                    continue
                eco.resolve_default(loan)
                del settle_at[i]
            before = agent.fees_paid
            loan = eco.loan(name, "bank", principal=100 * activity[i], bond=BOND_FRACTION * agent.liquid_reputation)
            fees_paid[t, i] = agent.fees_paid - before
            if unreliable[i] and draws[i] < P_DEFAULT:
                eco.default_loan(loan)
                settle_at[i] = (t + DELINQUENT_FOR, loan)
            else:
                eco.repay_loan(loan)
        before = np.array([eco.agents[n].dividends_received for n in names])
        eco.pay_dividend()
        dividends[t] = np.array([eco.agents[n].dividends_received for n in names]) - before
        if t + 1 in CHECKPOINTS:
            snapshots[t + 1] = np.array([eco.agents[n].reputation for n in names])

    reliable = ~unreliable
    early, late = reliable & (join == 0), reliable & (join >= 200)
    out = {}
    for when, rep in snapshots.items():
        standing = (rep / rep.sum()) / (activity / activity.sum())
        out[f"late_over_early_{when}"] = float(standing[late].mean() / standing[early].mean())
        out[f"unreliable_standing_{when}"] = float(standing[unreliable].mean() / standing[early].mean())
    rep = snapshots[HORIZON]
    out["gini_reputation"] = gini(rep[reliable])
    out["gini_activity"] = gini(activity[reliable])
    last = slice(HORIZON - 200, HORIZON)
    out["reliable_dividends_over_fees"] = float(dividends[last][:, reliable].sum() / fees_paid[last][:, reliable].sum())
    out["unreliable_dividends_over_fees"] = float(dividends[last][:, unreliable].sum() / fees_paid[last][:, unreliable].sum())
    top = activity >= np.quantile(activity, 0.9)
    recent = dividends[HORIZON - 100:]
    out["top_tenth_dividend_share"] = float(recent[:, top].sum() / recent.sum())
    out["top_tenth_activity_share"] = float(activity[top].sum() / activity.sum())
    out["top_tenth_reputation_share"] = float(rep[top].sum() / rep.sum())
    return out


def main():
    results = {}
    for decay in DECAYS:
        per_seed = [simulate(seed, decay) for seed in SEEDS]
        results[str(decay)] = {k: dict(mean=float(np.mean([s[k] for s in per_seed])), min=min(s[k] for s in per_seed),
                                       max=max(s[k] for s in per_seed)) for k in per_seed[0]}
    out = dict(provenance=run_provenance(), config=dict(agents=AGENTS, horizon=HORIZON, seeds=SEEDS, decays=DECAYS), results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    def cell(r, key, digits=3):
        v = r[key]
        return f"{v['mean']:.{digits}f} ({v['min']:.{digits}f} to {v['max']:.{digits}f})"

    rows = [
        ("late arrivals' standing relative to early, cycle 400", "late_over_early_400"),
        ("late arrivals' standing relative to early, cycle 800", "late_over_early_800"),
        ("unreliable agents' standing relative to reliable early agents, cycle 800", "unreliable_standing_800"),
        ("Gini of reputation, reliable agents", "gini_reputation"),
        ("Gini of activity, reliable agents", "gini_activity"),
        ("reliable agents: dividends / fees, last 200 cycles", "reliable_dividends_over_fees"),
        ("unreliable agents: dividends / fees, last 200 cycles", "unreliable_dividends_over_fees"),
        ("top tenth by activity: share of dividends, last 100 cycles", "top_tenth_dividend_share"),
        ("top tenth by activity: share of reputation", "top_tenth_reputation_share"),
        ("top tenth by activity: share of activity", "top_tenth_activity_share"),
    ]
    L = ["# Dividend concentration: results", "",
         f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}. "
         f"{AGENTS} agents, {HORIZON} cycles, {len(SEEDS)} seeds; mean (min to max over seeds).", "",
         "| measure | " + " | ".join(f"decay {d}" for d in DECAYS) + " |", "|---|" + "---|" * len(DECAYS)]
    L += [f"| {label} | " + " | ".join(cell(results[str(d)], key) for d in DECAYS) + " |" for label, key in rows]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
