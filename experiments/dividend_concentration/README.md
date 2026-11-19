# Dividend concentration

Started 2026-11-19. Serves the question behind the protocol's purpose: does reputation, and the dividend
that follows it, concentrate with those who arrived first or who are simply bigger, or does it track what
people do?

## Question

Under the current rules reputation is earned in proportion to fees paid on kept promises, and decays. So
there are three things a holder's share of reputation could follow:

1. how much they transact (their share of activity);
2. how long they have been here (early arrival);
3. how they behave (whether they keep their promises).

Which, and how does the decay rate change the answer?

Kind: a simulation, but the steady state is deductive. With decay `delta`, an agent paying fees `f` per
cycle converges to `f / (kappa * delta)` points with time constant `1 / delta`, whatever their history.
Without decay their points are `f * tenure / kappa`.

## Decision it feeds

The decay rate, and whether anything further is needed to keep early holders from entrenching.

## Setup

`Economy.current_rules` (1% fee with a 0.1 minimum, `kappa` = 0.04, fees paid out, reserve fund releasing 3%).
200 agents borrow from a bank every cycle. Loan size is `100 * a` where `a` is lognormal (median 1,
log-standard-deviation 1), fixed per agent. Half the agents are present from cycle 0; the rest join at a
uniformly random cycle up to 300. 80% are reliable. 20% are unreliable: each loan defaults with probability
0.1, after which they are delinquent for 5 cycles and then settle. Every loan is bonded with 20% of the
borrower's liquid reputation. 800 cycles. Five seeds (0 to 4), the same population in every arm.

Arms: decay 0.03 per cycle (the deployed value), 0.005, and 0 (no decay; no genesis allocation, since its
size is undefined).

Measures, for reliable agents unless stated: an agent's *standing* is their share of reputation divided by
their share of activity (1 means reputation exactly tracks activity).

## Predictions (written 2026-11-19, before running)

1. **Late arrivals catch up at the decay rate.** Mean standing of those who joined in cycles 200 to 300,
   relative to those present from cycle 0:

   | decay | at cycle 400 | at cycle 800 |
   |---|---|---|
   | 0.03 | 0.97 to 1.00 | 0.99 to 1.01 |
   | 0.005 | 0.55 to 0.67 | 0.93 to 0.97 |
   | 0 | 0.33 to 0.42 | 0.65 to 0.73 |

2. **With decay, inequality of reputation is inequality of activity.** At cycle 800 with decay 0.03, the Gini
   coefficient of reputation among reliable agents is within 0.02 of the Gini coefficient of their activity.
3. **Dividends return the fees.** Over the last 200 cycles, reliable agents collect between 1.0 and 1.15 times
   what they pay in fees (decay 0.03): a steadily active agent gets back their own fees, plus a little of what
   the unreliable forfeit.
4. **Behaviour matters.** Unreliable agents' standing is below 0.6 at cycle 800 (decay 0.03).
5. **Size does not compound.** The share of dividends going to the top tenth of agents by activity, over the last
   100 cycles, is within 0.03 of their share of activity (decay 0.03).

Failure would be: late arrivals still behind at cycle 800 with decay 0.03; or large agents holding a larger
share of reputation than of activity.

## Scope

Activity is exogenous: nobody transacts more because they hold reputation, and nobody is refused a loan for
lacking it. If lenders ration credit by reputation, early advantage could feed back into activity. That
loop is not modelled.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md` (mean and range over five seeds).

| prediction | outcome |
|---|---|
| 1. late arrivals catch up at the decay rate | Held in all six cells. Decay 0.03: 0.982 at cycle 400, 0.998 at 800. Decay 0.005: 0.598, 0.950. No decay: 0.369, 0.684. |
| 2. Gini of reputation within 0.02 of Gini of activity (decay 0.03) | Held: 0.492 and 0.492. |
| 3. reliable agents collect 1.0 to 1.15 times their fees | Held: 1.094 (1.078 to 1.105). |
| 4. unreliable agents' standing below 0.6 | Held, by a wide margin: 0.236. |
| 5. top tenth's dividend share within 0.03 of their activity share | Held: 0.360 against 0.370. |

What this shows:

- **Reputation follows what people do, not when they arrived.** With the deployed decay rate someone who joins
  late has 98% of an early member's standing after about 150 cycles. Without decay they are still at 68% after
  500 cycles and never catch up.
- **It does not compound with size.** The largest tenth of agents hold 36% of the reputation and 37% of the
  activity. Reputation is as unequal as activity is, no more.
- **Behaviour is what separates people.** An agent who defaults on one loan in ten has less than a quarter of
  the standing of a reliable agent with the same activity, and collects 52% of their fees back in dividends
  where a reliable agent collects 109%. The difference is a transfer from the unreliable to the reliable.
- **For a reliable agent the fee is roughly a deposit, not a cost.** In steady state they get their fees back
  as dividends. What they have given up is about `1 / delta` cycles' worth of fees held in the system: paid in
  while their reputation was building, returned as it decays after they stop.
- **The decay rate is also the forgiveness rate.** Slower decay makes a bad record last: the unreliable agents'
  standing is 0.24 at decay 0.03, 0.08 at 0.005 and 0.03 with none. This is a second reason, besides tracking
  how people change (`bayes_decay/`), not to make decay very slow.

Not settled: the feedback from reputation to activity (see Scope). If lenders give larger loans to those with
more reputation, early arrival could matter again through that channel.

### Re-run after the payout fund was adopted (2026-11-19)

Fees now reach holders through a payout fund released at the decay rate (`surge_fixes/`), and there is no
genesis allocation. Re-run under that design: every row is within 0.002 of the above except unreliable agents'
dividends over fees at decay 0.005 (0.198, was 0.211). All five predictions still hold. (The no-decay arm has
no decay rate to release at; it uses 3% per cycle.) `results/SUMMARY.md` is from the re-run.
