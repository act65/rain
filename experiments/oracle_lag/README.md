# Oracle lag

Started 2026-11-19. Serves the design choice of computing reputation off-chain: how often must the oracle run?

## Question

When a promise is resolved, some consequences are immediate (they happen in the contracts) and some wait for
the oracle:

| | on a default | on a kept promise |
|---|---|---|
| at once | the bond is destroyed; the promisor is flagged delinquent | the bond is returned |
| when the oracle next runs | the flat 100-point penalty | the reward (fee / point price) |

And the updater refuses a reward to anyone who is delinquent *when it runs*. What does a lag of `L` cycles
between resolution and the oracle's update cost, and whom?

Kind: mostly deductive; the simulation checks the reasoning and measures the one effect whose sign is not obvious.

## Decision it feeds

How often the oracle needs to run, and whether the flat penalty should move on-chain.

## Setup

`Economy.current_rules` with `oracle_lag` = 0, 1, 3, 6, 12 cycles. 100 honest agents each keep one promise per
cycle (fee 1 DMD, so 25 points). 10 defaulters do the same but default on every 20th loan (staggered), are
delinquent for 3 cycles, then settle; they bond 20% of their liquid reputation. One newcomer, honest, joins at
cycle 300. Genesis allocation sized for the fee flow. Measured over cycles 300 to 700. No randomness.

## Predictions (written 2026-11-19, before running)

1. **Honest agents in steady state are unaffected.** A constant flow of rewards delayed by `L` is the same
   flow. Their dividends over cycles 300 to 700 are within 1% of the no-lag case at every `L`.
2. **A newcomer pays for the lag once.** Their whole stream of dividends is shifted `L` cycles later, so its
   present value at the moment they join is `(1 + r) ** -L` of the no-lag value: 0.952, 0.864, 0.746 and 0.557
   for `L` = 1, 3, 6, 12 (within 0.02).
3. **Defaulters do not gain from the lag; they lose.** The flat penalty arrives late, which is worth about
   100 points for `L` cycles. But rewards for promises kept in the `L` cycles before a default fall due while
   they are delinquent and are lost for good (up to 3 of them, 25 points each, which would have earned for
   about 33 cycles). The second effect is larger, so defaulters' dividends over cycles 300 to 700 are lower
   with a lag than without: between 2% and 10% lower for `L` >= 1.

Failure would be: defaulters collecting more with a lag (then the penalty should be applied on-chain), or
honest steady-state agents losing more than 1%.

## Scope

Decisions are not modelled: nobody chooses to default because the oracle is slow. Other applications that
read the score instead of the delinquent flag would over-trust a defaulter for `L` cycles; that is not measured.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. honest steady-state agents within 1% | Held except marginally at `L` = 3: +0.3%, +1.0%, +1.0%, +0.9% for `L` = 1, 3, 6, 12. They gain slightly, because defaulters lose (below). Their reputation is identical at every lag (808.3). |
| 2. newcomer's present value is `(1 + r) ** -L` | Held: 0.956, 0.873, 0.753, 0.561 against 0.952, 0.864, 0.746, 0.557. |
| 3. defaulters lose 2% to 10% with a lag | Sign held; **the size was wrong for longer lags**: -6.9% at `L` = 1, then -20.8%, -19.6%, -16.9% at `L` = 3, 6, 12. |

What this shows:

- **A slow oracle does not help defaulters.** The late flat penalty is worth little; the bond and the
  delinquent flag, which are immediate, carry the deterrent. The flat penalty does not need to move on-chain
  for this reason.
- **A slow oracle costs newcomers, and only them.** Everything they earn arrives `L` cycles late: 5% of its
  value per cycle of lag at these rates. The oracle should run at least once per dividend cycle.
- **The lag punishes defaulters for promises they kept.** The updater refuses a reward to anyone delinquent
  *when it runs*. So promises kept honestly in the `L` cycles before a default go unrewarded if the oracle
  had not yet processed them. The loss is largest when the lag equals the time spent delinquent (3 cycles
  here), which is why it peaks at `L` = 3 and then eases. Nobody designed this; it is an interaction between
  two rules, and it makes the size of the penalty depend on the oracle's schedule.

A possible fix, not implemented: have the oracle decide eligibility as of the block in which the promise was
kept (it can read the delinquent flag at that block), instead of the updater checking at submission time.
Then the reward for a kept promise would not depend on when the oracle runs.

## Follow-up: eligibility decided when the promise was kept (2026-11-19)

The fix above was adopted. The oracle now reads the promisor's delinquent status as of the promise's own
position in the event log (`rain.reputation.process_promise_log`), and neither the updater nor the ledger
checks the flag when an update arrives. A promise kept while delinquent still earns nothing. The model
follows the same rule.

Re-running this experiment with that rule. Predictions (written before the re-run):

4. Honest agents and the newcomer are as before (predictions 1 and 2 unchanged).
5. Defaulters no longer lose rewards to the lag, so what is left is the late flat penalty, and the lag now
   helps them a little: their dividends over cycles 300 to 700 rise by roughly 1% to 2% per cycle of lag
   (100 points kept for `L` extra cycles, once every 20 cycles, on a reputation of a few hundred points):
   between +1% and +2% at `L` = 1, +3% to +6% at 3, +6% to +12% at 6, +12% to +22% at 12.

If 5 holds, the case for applying the flat penalty promptly comes back: either run the oracle every cycle or
move that penalty on-chain.

### Outcome of the follow-up (2026-11-19)

| prediction | outcome |
|---|---|
| 4. honest agents and the newcomer as before | Held: honest agents 0.9999 to 0.998 of the no-lag case; the newcomer 0.952, 0.863, 0.745, 0.555 against a predicted 0.952, 0.864, 0.746, 0.557. |
| 5. defaulters gain 1% to 2% per cycle of lag | **Right sign, too large.** They gain +0.3%, +1.0%, +2.2%, +4.8% at `L` = 1, 3, 6, 12: about 0.4% per cycle of lag. |

So with the fair rule a slow oracle does help defaulters, slightly, through the late flat penalty: under 1% if
the oracle runs within a cycle or two of each default. The earlier result (defaulters losing up to 21%) was
entirely the lost-rewards artefact, which is gone. The practical conclusion is the same as before and now
rests on one effect instead of two that pulled in opposite directions: **run the oracle at least once per
dividend cycle**, mainly so that newcomers are not kept waiting. Moving the flat penalty on-chain would remove
the remaining gain but is not worth doing for 0.4% per cycle.

(The results table in `results/SUMMARY.md` is from this re-run. The first run's numbers are in the Outcome
section above.)

### Re-run after the payout fund was adopted (2026-11-19)

With fees paid out through a fund released at the decay rate and no genesis allocation (`surge_fixes/`), the
results are the same to three decimal places: defaulters +0.3%, +1.0%, +2.2%, +4.8%; the newcomer 0.952, 0.864,
0.746, 0.556. `results/SUMMARY.md` is from this re-run.

### Re-run after the two-counter change (2026-11-19)

The contracts now keep two fading counters per account, reputation (promises kept) and a broken-promise
counter, and a default no longer takes a flat 100 points: it costs the bond and an entry on the broken
counter (`notes/bayesian-reputation.md`). The Treasury also reads its release rate from the reputation
contract, so the two can no longer differ. No prediction was written before this re-run; it was a check that
nothing else moved. `results/SUMMARY.md` is from the re-run.

There is no flat penalty left to arrive late, so the oracle's lag now delays only rewards and the
broken-promise record.

| lag | defaulters' dividends, relative to no lag | before |
|---|---|---|
| 1 | +0.1% | +0.3% |
| 3 | +0.35% | +1.0% |
| 6 | +0.7% | +2.2% |
| 12 | +1.6% | +4.8% |

Honest agents (0.9993 to 1.0000) and the newcomer (0.952, 0.864, 0.746, 0.557) are as before. The defaulters'
remaining gain is a third of what it was. My reading of it, not tested: rewards still waiting for the oracle
cannot be bonded, so with a lag the bond (20% of liquid reputation here) is smaller and a default destroys
less. The conclusion stands: run the oracle at least once per dividend cycle. One new cost of a lag: a lender
reading the broken counter on-chain sees a default `L` cycles late. The delinquent flag is still immediate.
