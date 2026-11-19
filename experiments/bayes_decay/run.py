"""
Claim under test: counts that decay by gamma = 1 - h per step predict almost as well as the exact
Bayesian filter when reliability changes with hazard h. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain import belief
from rain.provenance import run_provenance

HERE = Path(__file__).parent
A0, B0, USERS, STEPS = 8.0, 2.0, 2000, 300
HAZARDS = [0.0, 0.005, 0.02, 0.05]
GAMMAS = [0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 1.0]
SEEDS = [0, 1, 2, 3, 4]


def losses(outcomes, hazard):
    out = {
        "prior": belief.log_loss(np.full_like(outcomes, A0 / (A0 + B0)), outcomes),
        "static": belief.log_loss(belief.static_predictive(outcomes, A0, B0), outcomes),
        "exact": belief.log_loss(belief.exact_predictive(outcomes, A0, B0, hazard), outcomes),
        "matched": belief.log_loss(belief.forgetting_predictive(outcomes, A0, B0, 1 - hazard), outcomes),
    }
    for gamma in GAMMAS:
        out[f"gamma={gamma}"] = belief.log_loss(belief.forgetting_predictive(outcomes, A0, B0, gamma), outcomes)
    return out


def summarise(per_seed):
    keys = per_seed[0].keys()
    return {k: dict(mean=float(np.mean([s[k] for s in per_seed])), min=min(s[k] for s in per_seed), max=max(s[k] for s in per_seed)) for k in keys}


def main():
    results, control = {}, {}
    for hazard in HAZARDS:
        per_seed, per_seed_control = [], []
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            outcomes = belief.simulate_outcomes(rng, USERS, STEPS, A0, B0, hazard)
            per_seed.append(losses(outcomes, hazard))
            if hazard == 0.02:
                shuffled = np.stack([rng.permutation(outcomes[:, t]) for t in range(STEPS)], axis=1)
                per_seed_control.append(losses(shuffled, hazard))
        summary = summarise(per_seed)
        gaps = [(s["static"] - s["matched"]) / (s["static"] - s["exact"]) for s in per_seed] if hazard > 0 else None
        best = [min(GAMMAS, key=lambda g: s[f"gamma={g}"]) for s in per_seed]
        results[str(hazard)] = dict(summary=summary, gap_closed=gaps, best_gamma_by_seed=best)
        if per_seed_control:
            control = summarise(per_seed_control)

    out = dict(provenance=run_provenance(), config=dict(a0=A0, b0=B0, users=USERS, steps=STEPS, seeds=SEEDS), results=results, control=control)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    lines = ["# Decaying counts against the exact filter: results", "",
             f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}. "
             f"{USERS} users, {STEPS} promises, {len(SEEDS)} seeds; log loss, mean over seeds.", "",
             "| h | prior only | static | forgetting, gamma = 1 - h | exact | gap closed (mean, min to max) | best gamma (by seed) |",
             "|---|---|---|---|---|---|---|"]
    for hazard in HAZARDS:
        r = results[str(hazard)]
        s = r["summary"]
        gap = "n/a" if r["gap_closed"] is None else f"{np.mean(r['gap_closed']):.1%} ({min(r['gap_closed']):.1%} to {max(r['gap_closed']):.1%})"
        lines.append(f"| {hazard} | {s['prior']['mean']:.5f} | {s['static']['mean']:.5f} | {s['matched']['mean']:.5f} | {s['exact']['mean']:.5f} | {gap} | {r['best_gamma_by_seed']} |")
    lines += ["", "## Log loss by gamma (mean over seeds)", "", "| h | " + " | ".join(str(g) for g in GAMMAS) + " |", "|---|" + "---|" * len(GAMMAS)]
    for hazard in HAZARDS:
        s = results[str(hazard)]["summary"]
        lines.append(f"| {hazard} | " + " | ".join(f"{s[f'gamma={g}']['mean']:.5f}" for g in GAMMAS) + " |")
    lines += ["", "## Control (h = 0.02, outcomes shuffled across users)", "",
              f"prior {control['prior']['mean']:.5f}, static {control['static']['mean']:.5f}, forgetting {control['matched']['mean']:.5f}, exact {control['exact']['mean']:.5f}"]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
