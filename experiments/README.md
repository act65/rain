# Experiments

Each directory is self-contained: `python run.py` (from the repo root: `uv run python experiments/<name>/run.py`)
writes `results/results.json` (stamped with the commit that produced it) and `results/SUMMARY.md`.
Experiments depend on the `rain` library and never on each other.

When a run happens on a machine that has no git checkout (e.g. a synced copy on a VM), pass the stamp in:
`RAIN_COMMIT=$(git rev-parse HEAD) RAIN_DIRTY=1 python experiments/<name>/run.py`.

The economic experiments use `rain.model.Economy`, a pure-Python model of the protocol's accounting, and the closed
forms in `rain.economics`. The model is checked against the real contracts in
`tests/test_model_vs_contracts.py`.

**Two rule sets.** The first four experiments (`default_frontier/`, `fee_dynamics/`, `exit_scam/`, `sybil/`) study the ORIGINAL rules (a flat 25 points per kept promise, a fee
keeper, a treasury paying only its yield, no decay, free starting reputation). Their findings are why the
contracts changed. `Economy()` still gives those rules so the experiments stay reproducible;
`Economy.current_rules(...)` gives the rules the contracts now implement, and that is what the model test checks.
`Economy.genesis_rules(...)` is an intermediate design (fees paid out in full each cycle, with a genesis allocation), kept for `surge_fixes/`.
`current_rules/` re-asks the first four experiments' questions under them; read it for conclusions about the protocol as it stands. `bayes_decay/` and `dividend_concentration/` have randomness (five seeds each, stated in their READMEs); the rest are deterministic.

| experiment | directory | question | status |
|---|---|---|---|
| Default-rationality frontier | `default_frontier/` | How large a loan can a given reputation safely back? | run 2026-11-19 |
| Fee dynamics and farming | `fee_dynamics/` | Does the fee keeper keep reputation farming unprofitable, and where does the fee go over time? | run 2026-11-19 |
| Exit scam | `exit_scam/` | When does it pay to build reputation and then default on everything at once? | run 2026-11-19 |
| Sybil identities and vouching | `sybil/` | What does a disposable identity cost and what can it extract? | run 2026-11-19 |
| Anchored fee | `anchored_fee/` | Do a fixed price per point, decay and paying fees out give reputation a stable value? (led to the current contract rules) | run 2026-11-19 |
| Decay as Bayesian inference | `bayes_decay/` | How close do two decaying counters come to the exact Bayesian estimate of reliability? | run 2026-11-19 |
| The first four, under the current rules | `current_rules/` | The questions of the first four experiments, asked of the contracts as they now are | run 2026-11-19 |
| Dividend concentration | `dividend_concentration/` | Does reputation follow activity, early arrival or behaviour? (current rules) | run 2026-11-19 |
| Oracle lag | `oracle_lag/` | What does a delay between a promise resolving and the oracle's update cost, and whom? (current rules; led to a change in how rewards are decided) | run 2026-11-19, re-run after the change |
| Damping a surge | `surge_fixes/` | Which rule change keeps a point below its cost through a surge in activity? (the winner, a payout fund, is now in the contracts) | run 2026-11-19 |
| Collusion | `collusion/` | What does a record manufactured with confederates cost, whom can it rob, and how much trust in unknown counterparties is safe? | run 2026-11-19 |
| What a default really costs | `standing_value/` | Dividends, access to credit and the option to start again: the full account of a default on a ladder | run 2026-11-19 |

Each README states its predictions (written before the first run) and then the outcome.

## Shared conventions

- Time is in dividend cycles. `r` is the discount rate per cycle.
- `v` is the value of one reputation point: the present value of the dividends it will collect.
- A kept promise costs the fee `f = m * v * g` (`m` the keeper's safety margin, `g = 25` points).
- Baseline parameters of the original rules: `m = 1.5`, `r = 0.05`, `g = 25`, flat default penalty 100 points.
  (The current rules have no flat penalty: a default costs the bond and is recorded on a broken-promise counter.)
- "Demo" refers to the numbers produced by `scripts/run_simulation.py`: one 5 DMD dividend over 325 points
  (so `v = 0.3077` DMD per point), and a 1000 DMD loan at 5% against a 50-point bond.
