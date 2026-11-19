# Damping a surge in activity

Started 2026-11-19. Follows `current_rules/` part B: after a tenfold, lasting rise in activity a point is worth
1.37 times its cost for about four cycles, because fee income jumps at once while the supply of points takes
about `1 / delta` cycles to catch up. The start-up hole that the genesis allocation was added for
(`anchored_fee/`) is the same effect.

## Candidates

1. **Fixed issuance, floating price.** Each cycle a fixed number of points is minted and shared among those who
   kept promises, in proportion to the fees they paid. Supply is constant; the price of a point is whatever
   that cycle's fees divided by the issue comes to.
2. **Smoothed payout.** Every fee goes into the reserve fund; each cycle a fixed fraction `rho` of the fund is
   paid out. (The fund and its release already exist; today only the genesis allocation's share goes through it.)
3. **Vesting.** Newly earned points count for bonding at once but take part in dividends only after `W` cycles.

All three are modelled as options of `rain.model.Economy` and are NOT in the contracts.

## Decision it feeds

Which, if any, to implement.

## Setup

As `current_rules/` B: `kappa` = 0.04, `delta` = 0.03, `r` = 0.05, one honest bloc keeping 100 promises a cycle at a
1 DMD fee, genesis allocation at the steady supply unless stated. "Value / cost" is the discounted dividends a
point earned in a cycle goes on to collect, divided by what it cost that cycle. Four scenarios per arm:
start-up (from cycle 0), a tenfold rise at cycle 300, a tenfold fall at cycle 300, and a one-off grant of ten
cycles' fees at cycle 300. Value is measured with hindsight, so cycles before a shock are excluded: the
question is whether someone reacting to a shock can profit.

Arms: baseline (current rules); fixed issuance (2500 points per cycle); smoothed payout with `rho` = 0.03, 0.1,
0.3, and with `rho` = 0.03 and no genesis allocation; vesting with `W` = 3, 10, 33.

## Predictions (written 2026-11-19, before running)

1. **Fixed issuance** holds value / cost at `delta / (r + delta)` = 0.375 through every shock (within 0.01), because
   price and dividend move together. Start-up behaves like the baseline with a genesis allocation.
2. **Smoothed payout does not lower the steady value**: in steady state the fund pays out exactly what comes in,
   so value / cost is still 0.375. (I said otherwise when proposing it; that was wrong.)
3. **Smoothed payout at `rho = delta`** makes dividends rise at the same speed as supply, so value / cost stays
   near 0.375 through the tenfold rise (peak at most 0.40), the tenfold fall (trough at least 0.33) and the grant
   (peak at most 0.45). With `rho` = 0.1 the rise peaks between 0.6 and 0.8; with 0.3, between 1.0 and 1.2.
4. **Smoothed payout makes the genesis allocation unnecessary**: with `rho = delta` and no genesis allocation,
   value / cost is within 0.05 of 0.375 from cycle 0 (the fund fills at the rate supply grows).
5. **Vesting lowers the steady value** to `0.375 * ((1 - delta) / (1 + r)) ** W`: 0.296, 0.170 and 0.028 for `W` = 3, 10, 33.
   It reduces the peak after a tenfold rise (to between 0.9 and 1.15 for `W` = 3, below 0.8 for 10) by handing the
   over-reward to existing holders instead of new points.

If 2 to 4 hold, smoothed payout at `rho = delta` removes the exposure at no cost in steady state and replaces the
genesis allocation. Failure would be: smoothing lowering the steady value, or fixed issuance not holding 0.375.

## Scope

Step shocks only; a single bloc of honest users; no farmer agent (value / cost above 1 is taken as "farming pays").

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. fixed issuance holds 0.375 through every shock | Held for the rise and the fall (0.375 exactly). It does nothing for a one-off grant (peak 0.66, as the baseline) and nothing for start-up. |
| 2. smoothing does not lower the steady value | Held: 0.375 at every `rho`. |
| 3. `rho = delta`: rise at most 0.40, fall at least 0.33, grant at most 0.45; `rho` = 0.1 between 0.6 and 0.8; 0.3 between 1.0 and 1.2 | Held except the grant by a hair: rise 0.375, fall 0.375, grant 0.458. `rho` = 0.1 peaks at 0.70; 0.3 at 1.05 (above 1 for 3 cycles). |
| 4. `rho = delta` with no genesis allocation is within 0.05 of 0.375 from cycle 0 | Held exactly: 0.375 at every cycle. |
| 5. vesting lowers the steady value to 0.296, 0.170, 0.028 and cuts the peak | **Steady values wrong**: 0.324, 0.230, 0.075. I forgot that points still vesting are left out of the split, so each earning point collects more. Peaks 1.18 (`W` = 3, above my range, above 1 for 2 cycles), 0.84 (`W` = 10, above my 0.8), 0.27 (`W` = 33). |

What this shows:

- **Smoothed payout with the release rate equal to the decay rate removes the exposure entirely.** Value / cost is
  0.375 at start-up, through a tenfold rise and through a tenfold fall, because dividends and supply then move
  at the same speed. A one-off grant lifts it to 0.46. It costs nothing in steady state.
- **It also replaces the genesis allocation.** The fund starts empty and fills as supply grows. Keeping both
  double-damps (0.125 at cycle 0). Dropping the genesis allocation removes a deployment parameter that had to
  be guessed from expected activity.
- **The release rate has to track the decay rate.** At 0.1 the surge peaks at 0.70 (still safe); at 0.3 it is
  back above 1.
- **Fixed issuance works for changes in activity but not for grants or start-up**, and it gives up the fixed
  price of a point.
- **Vesting is the weakest.** It needs a long wait to work, and the wait is paid by every honest newcomer:
  with `W` = 10 a point is worth 23% of its cost instead of 37.5%.

One consequence of smoothing to be aware of: the Treasury holds a float of about `1 / rho` cycles of fees (33
at 0.03) instead of passing each cycle's fees straight through.

Not settled: gradual changes in activity, and a release rate that differs from the decay rate by design.

**Adopted (2026-11-19).** The contracts now pay fees out through a payout fund in the Treasury
(`Treasury.payoutFund`, `releasePerCycle`, `cycleInterval`), and the genesis allocation of reputation has been
removed. The deploy script sets the release to the decay per period and the cycle interval to the decay
period. A minimum interval between cycles was added so that a manager cannot empty the fund by starting
cycles back to back. `Economy.current_rules` follows the new design; this experiment's arms are built on
`Economy.genesis_rules`, the design it was run against, so its numbers still reproduce.
