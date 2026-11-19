# Collusion: manufacturing a record with a friend

Started 2026-11-19. Serves the claim that Rain's record is costly to fake, and the design of the reader
library (`rain/record.py`).

## Question

A borrower and a confederate pass a loan back and forth. Each round costs a fee and puts a kept promise on the
borrower's record. A lender who lends against the record then lends to the borrower, who defaults.

1. What does a manufactured record cost?
2. What does it take from a lender who believes the whole log?
3. Does weighing each entry by the reader's trust in the counterparty stop it, and what trust in *unknown*
   counterparties is safe?
4. What does that scepticism cost an honest borrower whose record is with someone else?

Kind: deductive. Everything below follows from the belief in `rain/record.py` and the value of a point. The
simulation checks the formulas against the model of the contracts, and the search over the attacker's choices
finds their best attack instead of assuming it.

## Decision it feeds

What the reference lender should assume about counterparties it does not know, and what the posts may claim
about a record being portable between lenders.

## Setup

`Economy.current_rules` (fee 1% with a minimum of 0.1, point price 0.04, decay 0.03 per cycle, discount rate
0.05), in a large steady economy. Interest 5%.

**The bank** reads the borrower's record with `rain.record.weigh` and offers the largest amount due at which it
believes the chance of default is at most 10% (`largest_amount_due`: thresholds Pareto with tail index 1 above
a floor of 100, shocks 2%). To a stranger that is 108.9 due, a principal of 103.7. The bank trusts itself fully
and gives every counterparty it does not know the same trust `t0`.

**The attacker** (Mallory) has `n` confederates. In cycle 0 each lends Mallory `M` at no interest and is repaid.
In cycle 1 Mallory takes the bank's largest offer and defaults. Mallory chooses `M` (41 values from 100 to
1e7) and `n` (0, 1, 2, 5, 10, 20) to maximise profit: the present value of everything Mallory and the
confederates pay and receive, dividends on the reputation they earn included, over 600 cycles.

Arms:

| arm | the bank's trust in unknown counterparties | confederates |
|---|---|---|
| A | (no bank) one wash of `M` = 1e3, 1e4, 1e5 | 1 |
| B | 1 (believes the whole log) | 1, `M` = 1e3, 1e4, 1e5 |
| C | 0, 0.5, 0.9, 0.99, 0.999 | 1, best `M` |
| D | 0, 0.1, 0.5, 0.9 | best `n` and `M` |
| D' | 0.5, and the bank knows the confederates are one group | best `n` and `M` |
| E | an honest borrower who repaid 1e4 to another real lender; the bank trusts that lender at 0, 0.5, 0.9, 0.99, 0.999, 1 | none |

Controls. B must show the bank losing (if a bank that believes everything is not robbed, the attack is not
implemented). And an honest borrower who climbs with the bank itself must be offered 1.089 times more after
each repayment at every `t0` (if not, the sceptical bank is just refusing everyone).

## Predictions (written 2026-11-19, before running)

Write `u = (1 - t0) ** n` for the bank's doubt that the confederates' loans were all empty, and `p0` = 0.918
for the survival probability the bank needs (0.90 / 0.98).

1. **A wash costs 0.625% of the amount** (within 2%): the 1% fee, less the 37.5% of it that comes back as
   dividends on the reputation it buys.
2. **A bank that believes the log loses the whole loan, without limit.** Mallory's profit over a stranger's is
   about `0.98 M` for each `M` in arm B (within 3%): the bank offers 1.089 `M` due.
3. **One confederate and partial trust: a bounded gain.** The largest offer Mallory can extract is
   `1 + (1 - p0) (1 / u - 1)` times a stranger's: 1.00, 1.08, 1.74, 9.1 and 83 times for `t0` = 0, 0.5, 0.9,
   0.99, 0.999 (within 5%). It is reached by claiming about that much and no more: a larger claim is believed
   less.
4. **Many confederates: any trust in unknown counterparties is unbounded exposure.** With `t0` > 0 the same
   multiple applies with `u = (1 - t0) ** n`, which falls geometrically in `n`, while the cost rises only
   linearly. In arm D the best attack at `t0` = 0.1, 0.5 and 0.9 uses the most confederates allowed (20) and
   takes more than 5, 10,000 and 100,000 times a stranger's loan respectively. At `t0` = 0 the best attack is
   no wash at all and the profit is a stranger's loan.
5. **A bank that knows the confederates are one group is back to prediction 3**: arm D' equals arm C at
   `t0` = 0.5, and the best `n` is 1.
6. **The same scepticism costs honest borrowers their record.** In arm E the bank offers 108.9, 109.0, 109.8,
   119, 1010 and 10,890 for trust 0, 0.5, 0.9, 0.99, 0.999 and 1 (within 2%). At trust 0.99 the borrower is
   still 92 rungs of a 5% ladder away from what they have already shown elsewhere.

Failure would be: a manufactured record that pays against a bank with `t0` = 0; a wash costing much less than
predicted; or the simulation disagreeing with the formula by more than 0.5% at the points checked.

## Scope

The bank lends once. Whether Mallory could first build real trust with the bank and then default is the
ladder's exit problem, measured in `standing_value/`. Trust is a number the bank is given; where it should come
from (the bank's own dealings, a web of trust, proof of personhood) is not modelled. Confederates cost nothing
to create. The threshold model's parameters are assumed, not fitted.
