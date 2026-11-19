# Fee dynamics and reputation farming

> **This experiment studies the original rules** (flat reward, fee keeper, yield-only treasury, no decay), which the
> contracts no longer use. Its findings are part of why they changed. For the same question under the current
> rules see `../current_rules/`.

Started 2026-11-19. Serves the claim in `notes/assigning-reputation.md` that "the economic value of the
reputation gained from a fulfilled promise is always less than the fee paid to create it".

## Question

The keeper sets the fee to `m * v * g`, where `v` is estimated from recent dividends as a perpetuity. But
dividends are the yield on accumulated fees, and every promise both adds a fee to the treasury and adds
`g` points to the supply. Two things can break the claim: the estimate of `v` can be wrong about the
future, and it can lag the present.

1. Along the path the system actually follows, is a promise ever worth more than its fee?
2. Where does the fee go over time?
3. What happens when dividends jump (someone funds the treasury) and the keeper lags?

Kind: partly deductive (the feedback loop below), partly a simulation of dynamics.

## The feedback loop

Let `rho = treasury / total reputation`. The fee is `c * g * rho` with `c = m * y / r`
(`rain.economics.fee_feedback_exponent`). One promise takes `rho` to `rho * (R + c g) / (R + g)`. So `rho`,
the value of a point and the fee all scale as `R ** (c - 1)`: with `c < 1` they decay as reputation is
issued, with `c > 1` they grow without bound. There is no stable level.

## Decision it feeds

Whether the keeper rule can stay as it is, and whether the default parameters (`m = 1.5`, `r = 0.05` per
cycle, 25 points per promise) are sensible.

## Setup

`Economy` with one "honest" bloc holding 10,000 points and making 100 kept promises per cycle. Each cycle:
(shock, if any) -> honest promises -> farmer promises (if any) -> dividend -> keeper update (3-cycle
window). The value of a promise made in cycle `t` is measured after the fact as the discounted dividends its
25 points go on to collect, and compared with the fee in force when it was made.

| arm | m | y | r | c | extra |
|---|---|---|---|---|---|
| A1 baseline | 1.5 | 0.004 | 0.05 | 0.12 | |
| A2 runaway | 1.5 | 0.004 | 0.004 | 1.5 | |
| A3 control | 0 | 0.004 | 0.05 | 0 | fee is zero after the first update |
| A4 shock | 1.5 | 0.004 | 0.05 | 0.12 | treasury multiplied by 10 at cycle 50 |
| A5 shock + farmers | as A4 | | | | a farmer makes up to 1000 wash promises per cycle while the current value exceeds the fee |

## Predictions (written 2026-11-19, before running)

1. **A1**: value / fee never exceeds `1/m = 0.667` (allowing 0.70) for any cycle from 5 on. Farming does
   not pay in the steady state.
2. **A1**: the fee decays as a power of total reputation with exponent `c - 1 = -0.88` (within 0.05),
   fitted over cycles 20 to 300.
3. **A2**: the exponent is `+0.5` (within 0.05): the fee grows without bound. Value / fee exceeds 0.667
   throughout, and exceeds 1 at cycle 50 (farming pays), because dividends per point are rising and the
   perpetuity ignores that.
4. **A3 (control that must fail)**: with no margin the fee is zero and every promise is profitable.
5. **A4**: value / fee is about 6.7 in the shock cycle (the fee is stale), about 1.7 in the next, and
   below 1 from then on. Farming pays for exactly two cycles.
6. **A5**: the farmer makes a profit and is at the 1000-promise cap in both of those cycles.

Failure would be: A1 showing value above fee in steady state (the anti-farming claim is false even
without shocks), or the fitted exponents disagreeing with `c - 1` (the analysis above is wrong).

## Scope

One honest bloc with constant activity, no response of honest users to the fee, a treasury that only
ever grows. A positive result for A1 does not show farming is unprofitable under other activity patterns.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. A1: value / fee at most 0.667 | Held: maximum 0.631, minimum 0.313. Farming never pays in the steady state. |
| 2. A1: fee exponent -0.88 | Held: fitted -0.888. |
| 3. A2: exponent +0.5; value / fee above 0.667 and above 1 at cycle 50 | Held: fitted 0.497; value / fee between 0.74 and 2.92, 1.46 at cycle 50. Farming pays in 170 of the 995 cycles evaluated. |
| 4. A3 control | Held: zero fee, every promise profitable. |
| 5. A4: value / fee 6.7, then 1.7, then below 1; farming pays for exactly two cycles | **Partly wrong.** The pattern after the shock is right but smaller (5.22, 1.31, 0.75), because value / fee was 0.52 before the shock, not 0.667. And farming "pays" for 31 cycles, from cycle 21: a promise kept 29 cycles before the shock still collects the larger dividends after it. I measured value with hindsight and did not think through what that implies. |
| 6. A5: farmer profits, at the cap for both cycles | Held: 1000 wash promises in each of cycles 50 and 51, none otherwise; 1.2 DMD of fees returned 2.4 DMD. |

What this shows:

- **The keeper has no anchor.** The fee is priced from dividends, and dividends come only from fees. With the
  default parameters the first keeper update cuts the fee from 0.1 to 0.0024 DMD, and it then falls as
  `R ** -0.89`: 0.0003 DMD by cycle 50, 0.00007 by cycle 300. A point is worth 0.000004 DMD at cycle 100. The
  anti-farming inequality holds, but only because both sides of it go to zero. Reputation priced this way
  cannot back any credit (see `default_frontier/`).
- **With `c = m y / r > 1` the opposite happens**: the fee grows without bound and farming is profitable for a
  long time, because the keeper's perpetuity assumes level dividends while they are rising.
- **Anyone who can foresee a rise in dividends can farm ahead of it.** The keeper only looks backwards. An
  announced grant to the treasury, or simply rapid growth in fee income, makes reputation bought beforehand
  worth more than its fee. This is the real exposure, more than the two-cycle lag.
- **A farmer who reacts only after the shock still profits**, and the cost falls on existing holders: their
  discounted dividends drop by 2.3 DMD (21%) while the farmer nets 1.1 DMD. The farmer's fees enter the
  treasury but only their yield is ever paid out.
- The absolute amounts are tiny because the whole fee-funded economy is tiny at these parameters. That is
  itself the first finding.

Not settled here: whether a fee with a floor, or a fixed fee with reputation issuance adjusted instead, gives
a stable level. That needs its own experiment.
