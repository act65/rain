# Is decaying reputation good Bayesian inference?

Started 2026-11-19. Serves the proposal (notes/bayesian-reputation.md) that reputation should be the
belief "how likely is this person to keep their next promise", and that decay is what that belief does
when people can change.

## Question

If a user's reliability can change (with probability `h` before each promise it is redrawn from the
population), the exact Bayesian estimate tracks a distribution over when the last change happened. A
contract cannot do that. It can keep two counters per user (kept, broken) and multiply both by `gamma`
each step. How much predictive accuracy does that cheap rule lose against the exact filter, and is
`gamma = 1 - h` the right setting?

Kind: empirical, on synthetic data from the stated model. It measures the size of an approximation; whether
real borrowers follow the model is a different question.

## Decision it feeds

Whether "two decaying counters" is an adequate on-chain representation of reputation, and how the decay
rate should be chosen.

## Setup

2000 users, 300 promises each, population prior Beta(8, 2), hazard `h` in 0, 0.005, 0.02, 0.05. Five seeds
(0 to 4), the same data for every predictor. Predictors of the next outcome: prior only; static (never
forgets); forgetting for `gamma` on a grid from 0.90 to 1.00; exact. Metric: mean log loss over all
predictions; reported as mean and min to max over seeds. "Gap closed" is
`(static - forgetting) / (static - exact)`.

Control that must fail: with each user's outcomes replaced by another user's at every step (so there is
nothing individual to learn), no predictor should beat the prior.

## Predictions (written 2026-11-19, before running)

1. `h = 0`: static, forgetting at `gamma = 1` and exact are identical; any `gamma < 1` is worse.
2. `h > 0`: log loss is ordered exact < forgetting(`1 - h`) < static < prior only.
3. `h > 0`: forgetting at `gamma = 1 - h` closes at least 70% of the gap between static and exact.
4. The best `gamma` on the grid is within 0.03 of `1 - h`.
5. Control: every predictor is within 0.002 of the prior's log loss, or worse.

Failure would be: forgetting closes little of the gap (then two counters are not enough), or the best
`gamma` is far from `1 - h` (then the decay rate cannot simply be read off the rate of change).

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`. Seeds agree closely (the spread of "gap closed" across seeds is under 2 points).

| prediction | outcome |
|---|---|
| 1. `h = 0`: all three identical, `gamma < 1` worse | Held. |
| 2. ordering exact < forgetting(`1 - h`) < static < prior | Held for every `h > 0`. |
| 3. forgetting at `gamma = 1 - h` closes at least 70% of the gap | **Wrong.** 34.7% at `h = 0.005`, 70.0% at 0.02 (69.3% in the worst seed), 86.7% at 0.05. |
| 4. best `gamma` within 0.03 of `1 - h` | **Wrong in what it implies.** The best `gamma` is 0.97, 0.94 and 0.90 or lower (the edge of the grid) for `h` = 0.005, 0.02, 0.05. It is within 0.03 only for the smallest `h`. The counts should be forgotten 2 to 6 times faster than people change. |
| 5. control | Held: with outcomes shuffled across users every predictor is worse than the prior (0.5056 to 0.5079 against 0.5013). |

What this shows:

- **Two decaying counters are enough, if the decay rate is tuned.** At the best `gamma` on the grid, forgetting
  closes 82%, 93% and 97% of the gap between never forgetting and the exact filter.
- **The decay rate is not the rate of change.** Setting `gamma = 1 - h` forgets too slowly. Across the three
  hazards the best `1 - gamma` is close to `0.42 * sqrt(h)` (0.030, 0.059, 0.094 against 0.03, 0.06, at most 0.10).
  That is what a bias-variance trade-off predicts: forgetting faster adds noise in proportion to `1 - gamma`,
  forgetting slower leaves stale evidence in proportion to `h / (1 - gamma)`, and the sum is smallest when
  `1 - gamma` is proportional to `sqrt(h)`. I noticed this after seeing the results; the constant 0.42 is fitted
  to three points and belongs to this prior.
- **Never forgetting is nearly useless when people change.** At `h = 0.05` the static estimate barely beats the
  prior (0.49996 against 0.50094).

Not settled: the grid stops at 0.90, so the optimum for `h = 0.05` is not located; and the data come from the
model itself. Fitting `gamma` to real promise logs by maximising predictive likelihood is the next step once
there are any.
