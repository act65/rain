# Graduation: outgrowing a guarantor

Started 2026-11-19. `vouching/` ended with a newcomer who needs their guarantor for ever: a sceptical lender
learns nothing from guaranteed loans and never raises its own. This experiment tests a rule that lets a
record made under a guarantee count, without reopening the attacks of `collusion/` and `vouching/`.

## The rule

`rain.record.graduated_credit`. A lender accepts from a borrower, unsecured, at most

    min( evidence,  growth x own + cost since )

- **evidence**: the largest amount the borrower has repaid to anyone (never less than a stranger's loan). If
  they are genuine this is what they have shown they are good for.
- **own**: the largest amount they have repaid to this lender, unsecured. Each repayment raises the next loan
  by `growth` = 1 + the interest rate at most, so repaying in order to default later returns nothing.
- **cost since**: the fees they have sunk on kept promises since then, less the part that returns as
  dividends (62.5% of each fee is sunk at the usual parameters). A record is worth, as credit, what it cost.

It comes from three earlier results. `first_loan/`: below what a borrower is known to be good for, raise as
fast as the exit bound allows, and where opportunists can return, start at the price of an identity. Here the
record is the identity, and its price is its fees. `collusion/`: evidence from a counterparty the reader does
not trust is worthless *as belief*; but the rule does not need belief, only that being fake does not pay.

## A correction to `vouching/` first

`vouching/` reported that a fake borrower's guaranteed loan costs the ring 601 per 10,000: the bank's
interest, 476, and fees of 125. The interest is not a cost. There the loan was taken and repaid in the same
cycle. A loan that is outstanding for a cycle gives the ring 9,524 now for 10,000 a cycle later, which at a
discount rate equal to the interest rate is worth nothing either way. Only the fees are sunk. This is why the
rule counts fees and not interest.

## Questions

1. Can any ring profit against a lender using the rule?
2. How long does an honest newcomer need their guarantor?

Kind: deductive (a cash-flow argument), checked by simulating the ring's strategies in the model of the
contracts with loans outstanding for a cycle.

## Setup

As `vouching/`: fee 1%, point price 0.04, decay 0.03, discount rate and interest 5%, shocks 2%; a stranger is
offered 100 due; Sam, the guarantor, is good for 10,000 with the bank. Loans last one cycle.

**The ring** is Sam and a fake borrower. Each cycle up to `T` the fake borrower repays last cycle's loans and
takes new ones: the bank's unsecured offer, and (by variant) a guaranteed loan of `X`, or a wash of `X` with a
confederate at no interest, every cycle or only once. The unsecured loan taken in cycle `T` is not repaid.
Searched: `T` from 0 to 60; `X` = 1,000, 10,000, 100,000; four variants. Profit is the ring's present value,
net of a stranger's default.

**The honest newcomer** borrows 10,000 a cycle in total: as much as the bank offers unsecured, the rest
guaranteed by Sam.

Controls that must fail, each a weaker rule:

- *evidence alone*: the bank offers the largest amount repaid to anyone;
- *no growth limit*: the bank offers `evidence` as soon as one unsecured loan has been repaid to it;
- *cost counted every time*: the bank adds the whole sunk cost to every offer instead of the cost since the
  last repayment.

## Predictions (written 2026-11-19, before running)

1. **A guaranteed loan outstanding for a cycle costs the ring its fees: 125 per 10,000** (within 1%), not 601.
2. **Under the rule, no strategy in the search beats a stranger's default.** The best gain is 0 (do nothing
   but take the stranger's loan), and every strategy that manufactures a record loses.
3. **Each control is robbed.** Evidence alone: the ring gains about 8,900 with `X` = 10,000 (one guaranteed
   loan, then default). No growth limit: about 8,400 (one more cycle). Cost counted every time: a gain that
   grows with `T`.
4. **An honest newcomer outgrows the guarantor in 42 to 45 cycles.** The unsecured offer follows
   `next = 1.05 x last + 62.5` from 162.5, and the guaranteed part falls to zero when it reaches 10,000.
   Without a guarantor the offer stays at 100.
5. **A reputation point is worth 0.025 of first-rung credit**: the point price times the sunk share of a fee
   (0.04 x 0.625). A stranger who has earned `n` points on kept promises, to anyone, is offered `100 + 0.025 n`.

Failure would be: any strategy with a positive gain under the rule; or a control that is not robbed.

## Scope

The ring discounts at the same rate as everyone else; a ring that values the dividends on its reputation more
than the lender assumes has sunk less than the rule credits. The rule protects against borrowers who intend
to default, not against a genuine borrower who has overstated what they can carry by washing a large amount
(they would pay for the privilege and then fail). Whether a lender wants to drop the guarantor (it bears the
shock risk itself afterwards) is not modelled; it is profitable to lend unsecured to a known borrower
(`first_loan/`), and that is all that is assumed.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. a guaranteed loan outstanding a cycle costs the ring 125 per 10,000 | Close, and outside the 1% I set: 128.6. The reputation the fees buy is credited when the loan is repaid, a cycle after the fees are paid, so slightly less of them comes back. The point stands: fees, not the 601 reported in `vouching/`. |
| 2. under the rule no strategy beats a stranger's default | Held: of 671 strategies the best is to make no record at all (gain 0). Every strategy that manufactures a record loses, from 0.36 (one wash of 1,000) to 10,833 (washing 100,000 every cycle for 61 cycles). |
| 3. each control is robbed | Held, by more than I wrote, because the search also tried larger washes than the guaranteed loan I had in mind: evidence alone loses 93,519 to one wash of 100,000; no growth limit, 89,027; cost counted every time, 23,493 after 21 loans. |
| 4. an honest newcomer outgrows the guarantor in 42 to 45 cycles | Held, after two changes described below: the guaranteed part reaches zero in cycle 44. The unsecured offer goes 100, 168, 239, ..., 8,258 at cycle 40. Alone it stays at 100. |
| 5. a reputation point is worth 0.025 of first-rung credit | Held: 2,500 points earned by washing raise the offer from 100 to 162.50. |

Two things were changed after the first run, both in favour of the honest newcomer and neither touching the
attack search's conclusion (which was re-run and still finds no profitable strategy):

- **The rule ignored fees sunk while an unsecured loan was outstanding.** I had written "cost since the last
  repayment", so a guaranteed loan repaid just before the unsecured one in the same cycle never counted, and
  the offer grew by 5% a cycle only (704 after 40 cycles). The cash-flow argument allows every cost to count
  once; the right window is "since the last unsecured loan was made". That needs each promise's creation
  time, which the log has and `rain.record.Entry` now carries.
- **The newcomer's first guaranteed loan is now for the whole 10,000.** Splitting the need between the two
  loans from the first cycle left the largest single repayment at 9,900, and the offer stopped there.
  "Evidence" is the largest single promise kept, not the total carried at once; that is a limitation of the
  rule as written.

What this shows:

- **A guarantor is a bridge, not a permanent crutch.** Under a guarantee the newcomer shows at once what they
  can carry, and every loan sinks fees. The lender can turn both into unsecured credit at a rate no ring can
  exploit. At a 1% fee and 5% interest it takes 44 loans; the guarantor's expected cost over that time is
  3,176, against 3,937 for vouching for ever.
- **The rule needs no trust and no belief.** It does not ask who the counterparties were. A ring is free to
  manufacture any record; the record buys only as much credit as it cost. This is "fees as the cost of
  faking" as a mechanism: the fee is what makes a record usable by a lender who knows nothing about anyone.
- **Reputation gets a third job.** Beside a share of fees and a standing to lose, it is a receipt for sunk
  cost: 0.025 of unsecured credit per point earned, from any lender who uses this rule.
- **Trust is still faster.** A lender who knows the counterparties can use the record at face value. The rule
  is the floor under that: what a record is worth to a stranger.
- **All three parts of the rule are needed.** Each control drops one and is robbed.

What it does not show: that lenders would choose to drop a guarantor (they take on the shock risk when they
do); what happens when a ring values its dividends more than the lender assumes; or a version of "evidence"
that adds up loans carried at once.
