# What should the fees pay for?

Started 2026-11-20. Serves the design decision of where fee revenue goes.

## Question

Every promise pays a fee, and the fee is what makes a record costly to fake (`collusion/`). At present fees are
paid out as a dividend to holders of reputation. That was meant to give reputation a value that a defaulter
would lose. It cannot do that job (`anchored_fee/`, `current_rules/`: a point is worth less than it cost, or it
could be farmed), and what deters default is the loss of credit. So the dividend is a rebate of 37.5% of each
fee, paid to anyone who keeps promises, a ring washing loans included.

Where else could the revenue go, and what does each choice do to (1) the cost of faking a record, (2) the cost
to an honest user, (3) what a ring that produces nothing can take out?

Kind: deductive. Each rule's payouts are a formula; the simulation is a check on the arithmetic.

## Decision it feeds

Whether to keep the reputation dividend, and whether part of the fee should pay for work (carrying notes to the
chain, running the oracle).

## Setup

Fee 1% of the amount promised, discount rate 5% a cycle, decay 3%. An economy of honest users promising 1e6 a
cycle, of which 2% is defaulted on. A ring adds its own promises. Seven rules for the revenue:

| rule | the fee goes to |
|---|---|
| 1. dividend (current) | holders of reputation, in proportion, through the payout fund |
| 2. burn | nobody |
| 3. counterparty | the promisee of the promise that paid it |
| 4. insurance | promisees of broken promises: up to a share `c` = 50% of what they lost, pro rata if the pool is short |
| 5. work | a share `s` = 50% to whoever presents the promise to the chain, the rest as rule 1 |
| 6. per identity | every identity equally |
| 7. forfeitable dividend | as rule 1, but a default destroys the defaulter's reputation |

Measured for each: the net cost of washing one unit (fee less everything that comes back to the pair, in present
value); the net cost to an honest promisor of one unit; the share of the revenue taken by a ring that keeps no
real promise; and the trust in unknown counterparties below which no ring gains (the method of `collusion/`
part G, with the wash cost of the rule).

Control. Rule 1 must reproduce `collusion/`: a wash costs 0.625% and the safe trust is 3.3%.

## Predictions (written 2026-11-20, before running)

1. **Control.** Rule 1: a wash and an honest promise each cost 0.625% net; safe trust 3.3% (within 5%).
2. **Burning makes a record dearest.** Rule 2: both cost 1%. Safe trust rises in proportion to the net cost,
   to 5.3% (within 10%).
3. **Paying the counterparty makes a record free.** Rule 3: a wash costs nothing, because the confederate
   receives the fee. Safe trust is zero: any trust at all in unknown counterparties can be robbed.
4. **Insurance is drained.** Rule 4: a ring that lends to itself and defaults is paid `c` for a fee of 1%, so
   it profits whenever its claim is honoured at more than 2% of face. With fake claims ten times the honest
   ones it takes 91% of the pool, and honest promisees recover a tenth of what they did without the ring.
5. **Paying for work costs as much resistance as the work can be done by the payer.** Rule 5 with `s` = 50%: a
   ring that presents its own promises pays 0.3125% net per unit washed (safe trust about half of rule 1's);
   if the ring cannot present its own, 0.8125%.
6. **Paying identities pays whoever makes identities.** Rule 6: a ring with `k` free identities among `N`
   honest ones takes `k / (N + k)` of all revenue without making a promise: 91% at `k = 10 N`.
7. **No rule makes faking dearer than honest use.** In every rule the net cost of a wash is at most the net
   cost of an honest promise of the same size: a payout that is a function of the log cannot tell them apart.
8. **Forfeiting the dividend on default deters little.** Rule 7: a borrower who has climbed a ladder growing
   1.089 a loan holds reputation worth 3.4% of the amount now due (within 5%). That is the most the forfeit
   adds to the cost of defaulting.

Failure would be: any rule under which a wash costs more than an honest promise (prediction 7 wrong, and the
dividend's job could be done after all); or rule 1 failing the control.

## Scope

One fee rate. The honest economy is in a steady state. Rules are not combined beyond rule 5. What the work is
worth (whether carriers would carry notes for half the fee) is not modelled. Rule 4 has no gatekeeper on
claims; one that a ring cannot pass would need the trust that `collusion/` shows is the scarce thing.

## Outcome (2026-11-20)

Numbers are in `results/SUMMARY.md`. The control held: under the current rules a wash costs 0.6250% in the
model of the contracts and the safe trust is 3.32%. Only rules 1 and 7 run through the model; the others are
not implemented in it, and their rows are the formulas evaluated.

| prediction | outcome |
|---|---|
| 1. control: 0.625%, safe trust 3.3% | Held. |
| 2. burn: 1%, safe trust 5.3% | Held: 5.25%. |
| 3. counterparty: a wash is free, safe trust zero | Held. |
| 4. insurance is drained: a ring with ten times the honest claims takes 91% of the pool | Held: 90.9%, and honest promisees recover 5.5% of their losses where they recovered 50%. I misstated the break-even: the ring profits while claims are paid at more than 2% of the cover promised, which is 1% of face. |
| 5. work at a 50% share: 0.3125% if the ring presents its own promises, 0.8125% if it cannot | Held: safe trust 1.67% and 4.29%. |
| 6. per identity: ten identities for each honest one take 91% | Held. |
| 7. no rule makes faking dearer than honest use | Held in all seven. Under rule 3 a wash is cheaper than an honest promise by the whole fee. |
| 8. forfeiting the dividend takes 3.4% of the amount due | **The number was wrong: 3.06%** (model and formula agree). I counted the fee on the loan being defaulted on, which earns nothing. Outside the 5% I allowed. The substance holds: it is small against the loan. |

What this shows:

- **The fee has two jobs that pull against each other.** A record should cost something to make, which wants
  the fee not to come back. Honest use should be cheap, which wants it to. No rule separates them, because a
  payout is computed from the log and on the log a wash and a kept promise are the same thing.
- **So every unit returned to honest users is returned to rings.** The rules differ only in how much comes
  back (nothing under burning, 37.5% under the dividend, everything under a counterparty rebate) and in
  whether someone who makes no promises at all can take it (insurance claims, identities).
- **Three rules are out.** Paying the counterparty makes a record free. Paying claims or identities pays
  whoever can manufacture claims or identities, and both are free to manufacture.
- **Paying for work is a fee cut for whoever can do the work themselves.** A ring presents its own promises.
  A share for presenters is safe only where the payer cannot be the presenter, and the protocol cannot tell.
  A carrier is better paid by the parties to the note, in the script.
- **The dividend's job, stated correctly.** The revenue has to go somewhere. A recipient outside the system
  collects a rent on every promise, washes included. Returning it to payers on demand makes the fee no cost at
  all. The reputation dividend returns it to the people who paid, slowly, in proportion to promises kept, and
  in a way that cannot return more than was paid (the fund holds 0.04 per point). It lowers the safe trust from
  5.25% to 3.32%, and neither figure is enough to help an honest borrower with a record elsewhere
  (`collusion/` part E), so little is lost.
- **It does not deter default and should not be described as doing so.** Forfeiting it would add 3% of the
  amount due to the cost of defaulting.

Decision: keep the dividend. Change what the documentation says it is for: the least harmful way to give the
revenue back. Do not add a protocol payment for carriers or an insurance pool.

Not examined: lowering the fee and burning it (a 0.625% fee burned costs a wash the same as a 1% fee with the
dividend, with no Treasury, no payout fund and nothing for a patient ring to recover, `patient_ring/`; but it
destroys the revenue). That comparison turns on what the destroyed revenue is worth to users, which is a
preference, not a computation.
