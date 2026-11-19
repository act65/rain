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
