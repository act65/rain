# An anchored fee: fixed price per point, with decay

Started 2026-11-19. Follows `fee_dynamics/`, which found that the fee keeper has no anchor: the fee and the
value of a point both drift to zero.

## Proposal under test

- **Idea 1, a fixed price per point.** The fee is set from outside (a fixed amount here; a percentage of the
  promise in practice). A kept promise earns `fee / kappa` points. There is no keeper.
- **Idea 2, decay.** Every point shrinks by a fraction `delta` per cycle.
- **Idea 3 (an arm), pass-through.** Fees are paid out as dividends instead of being kept as
  treasury capital that only pays its yield.

These rules are modelled in `rain.model.Economy` (options `point_price`, `decay_rate`, `pass_through`). When this
experiment was first run they were proposals; all three were then adopted and are now in the contracts (see the end).

## Question

Do ideas 1 and 2 give a stable value for reputation and keep farming unprofitable, with and without idea 3?

Kind: deductive for the steady state (`rain.economics.steady_state_supply`,
`pass_through_value_over_cost`), a simulation for the approach to it and for shocks.

## Decision it feeds

Which of the three rule changes to implement in the contracts.

## Setup

As `fee_dynamics/`: one honest bloc starting with 10,000 points, 100 kept promises per cycle, `y = 0.004`,
`r = 0.05`. Fee 1 DMD per promise and `kappa = 0.04` DMD per point, so a promise still earns 25 points.
"Value / cost" is the discounted dividends a point bought in a cycle goes on to collect (allowing for its
decay), divided by `kappa`. Farming pays when it exceeds 1.

| arm | rules | delta |
|---|---|---|
| B0 | current keeper (reference; equals `fee_dynamics` A1) | 0 |
| B1 | ideas 1 + 2, treasury keeps fees and pays yield | 0.03 |
| B2 | ideas 1 + 2 + 3 | 0.03 |
| B1s, B2s | as B1, B2 with slow decay | 0.005 |
| B1-shock, B2-shock | at cycle 50: B1's treasury is multiplied by 10; B2 receives a grant of 10 cycles' fees, paid out at once | 0.03 |
| B1-farm, B2-farm | the shock arms plus a farmer who makes up to 1000 wash promises per cycle whenever a point's expected value exceeds `kappa` | 0.03 |

## Predictions (written 2026-11-19, before running)

1. **Supply settles** at `F (1 - delta) / (kappa delta)` (80,833 points for `delta = 0.03`) within 2% by cycle 200,
   in B1 and B2.
2. **B2 is stationary**: value / cost converges to `delta / (r + delta)` = 0.375 (within 0.01) by cycle 200, and
   to 0.091 for `delta = 0.005` (by cycle 1000). Farming never pays in the steady state, with no parameter to tune.
3. **B2's start-up is the weak point**: while supply is far below its steady level each point collects a large
   share of the fees. Value / cost at cycle 0 is between 0.8 and 1.1. I do not know which side of 1.
4. **B1 is not stationary**: the treasury grows without limit while supply settles, so value / cost rises
   roughly linearly and crosses 1 at about cycle 650 (within 30). Ideas 1 and 2 alone postpone the problem.
   At cycle 100 it is about 0.17.
5. **Shocks**: B2's value / cost in the shock cycle stays below 0.75 and the farmer makes no promises. B1's is
   between 0.8 and 1.0 and the farmer makes none either. (The keeper reached 5.2 in `fee_dynamics` A4.)

Failure would be: supply not settling, B2 not converging to `delta / (r + delta)`, or a farmer profiting
after a shock in B2.

## Scope

Constant honest activity, a fixed fee, no response of users to the value of reputation. The steady state
assumes activity continues; what happens when activity falls is not tested.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. supply settles at 80,833 within 2% by cycle 200 | Held: 80,678 at cycle 200 (0.2% below), 80,833 by cycle 650. Slow decay: 497,500 as predicted, reached by about cycle 3000. |
| 2. B2 converges to `delta / (r + delta)` | Held: 0.376 at cycle 200 and 0.375 from then on; 0.091 by cycle 1000 with slow decay. |
| 3. B2 start-up between 0.8 and 1.1 | **Wrong: it is 1.25** (1.37 with slow decay). Farming pays in the first cycles. A farmer who makes 1000 wash promises in cycle 0 turns 1000 DMD of fees into 1292 DMD of dividends. By cycle 5 the ratio is 0.89. |
| 4. B1 crosses 1 at about cycle 650; 0.17 at cycle 100 | Held: crosses at cycle 654; 0.175 at cycle 100. With slow decay it crosses at cycle 2731. |
| 5. shocks: B2 below 0.75 with no farming; B1 between 0.8 and 1.0 with no farming | Partly. B2 reaches 0.79 (not 0.75), still below 1, and the farmer does nothing at the shock. B1 is 0.89 at the shock and the farmer does nothing then, **but** the larger treasury brings the crossing forward to cycle 203, which I did not predict. |

What this shows:

- **Ideas 1 and 2 fix the collapse.** A point is worth between 0.002 and 0.04 DMD instead of 0.000004, the fee
  stays at 1 DMD, and total reputation settles instead of growing for ever.
- **Ideas 1 and 2 alone are not stationary.** The treasury keeps every fee, so its yield grows without limit
  while supply is fixed, and the value of a point climbs until it passes its cost: at cycle 654 here, at
  cycle 203 after a large grant. From then on wash promises cost nothing net. In the farmer arm they hold
  value / cost at 1 and average about 560 wash promises a cycle against 100 honest ones. Reputation then
  measures willingness to pay fees, not promises kept.
- **Adding idea 3 makes it stationary at any parameters**: value / cost is `delta / (r + delta)`, below 1 by
  construction, and a tenfold grant does not change that.
- **But idea 3 needs a start-up rule.** While supply is far below its steady level, a few points collect all
  the fees. Starting supply at its steady level, or making new points wait before they earn (idea 8), would
  close this; neither is tested here.
- **Slower decay means cheaper reputation in steady state.** With `delta = 0.005` a point is worth 9% of its
  cost against 37.5% at 0.03. Decay rate and the value of reputation are tied together.

Not settled: a middle course for the treasury (keep some capital, pay out the rest; or cap the endowment),
the start-up rule, and behaviour when honest activity falls.


## Follow-up: a start-up rule (2026-11-19)

Idea 3 was adopted, so its start-up hole needs closing. Candidate: **nobody starts with reputation; the
treasury holds a genesis reserve of points equal to the steady-state supply, which decays like any other
points.** The reserve's share of each dividend is not paid to anyone: it stays in the treasury and is part
of the next cycle's pool. So early fees are paid out later, once real users hold most of the points. No
new power and no pot of money is created.

Arms `B3_*`: honest users start at zero; reserve of 1, 0.5 and 2 times the steady supply; one arm with the farmer.

Predictions (written before running):

6. With a full-sized reserve, value / cost stays below 1 at every cycle. The held-back money makes early
   dividends per point several times the steady level for a dozen cycles, so the peak is well above 0.375:
   between 0.7 and 0.95. The farmer makes no promises.
7. A half-sized reserve does worse (higher peak, possibly above 1); a double-sized one does better.

Failure would be: a peak above 1 with the full-sized reserve. Then the held-back share should not be rolled
over, and should go to a separate reserve fund instead.

### Outcome of the roll-over rule (2026-11-19)

| prediction | outcome |
|---|---|
| 6. full-sized reserve: peak between 0.7 and 0.95, no farming | **Wrong.** The peak is 1.29 (at about cycle 5) and the farmer makes 6000 wash promises in cycles 2 to 7 for a profit of 335 DMD. Rolling the money over only postpones the excess by a few cycles; it still reaches the few points that exist early. |
| 7. half-sized worse, double-sized better | Held (peaks 1.50 and 1.10), but even the double-sized reserve is above 1. |

So, as stated above, the held-back share should not be rolled over.

### Second candidate: a reserve fund released slowly (2026-11-19)

The reserve's share of each dividend goes into a fund. A fixed fraction of the fund is added to each
cycle's dividend. Arms `B4_*`: release fraction 0 (never), 0.015 and 0.03 per cycle; a half-sized reserve;
farmers; slow decay.

Predictions (written before running):

8. Never released: value / cost is exactly `delta / (r + delta)` = 0.375 from cycle 0, because total supply
   is at its steady level from the start.
9. Released at the decay rate (0.03): the fund peaks at about 20 cycles' fees around cycle 30, which lifts
   dividends by at most about 60%. Peak value / cost between 0.45 and 0.6; never above 1; the farmer makes
   no promises.
10. Half-sized reserve, released at the decay rate: higher early values than 9, since supply starts low.
    I expect the peak to stay below 1 but am not confident.

### Outcome of the reserve fund (2026-11-19)

| prediction | outcome |
|---|---|
| 8. never released: exactly 0.375 from cycle 0 | Held, nearly: 0.367 at cycle 0 rising to 0.375 (the reserve was sized at the supply before decay, 3% above the steady level). |
| 9. released at the decay rate: peak between 0.45 and 0.6, no farming | Held: peak 0.543 at about cycle 20; the farmer makes no promises at any cycle. |
| 10. half-sized reserve: higher, probably below 1 | Held: peak 0.682 at cycle 0; no farming. |

With slow decay (0.005, release 0.005) the peak is 0.135 against a steady 0.091.

**Adopted.** The contracts now implement ideas 1, 2 and 3 with this start-up rule: a genesis allocation of
reputation held by the Treasury, whose dividend share goes to a reserve fund that releases a fixed fraction
of itself into each cycle (`RainReputation` constructor, `Treasury.reserveFund`). The size of the genesis
allocation is a deployment parameter: an estimate of `fees per period / point price / decay rate`. Getting
it wrong by a factor of two in the low direction still leaves value below cost here. What happens if activity
turns out far higher than assumed is not tested.

**Superseded in part (2026-11-19).** The genesis allocation and its reserve fund were replaced by a payout
fund that all fees pass through (`surge_fixes/`), which closes the start-up hole without a parameter to guess
and also covers surges in activity. Ideas 1 to 3 stand.
