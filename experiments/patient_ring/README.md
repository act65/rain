# A ring that is more patient than the lender assumed

Started 2026-11-19. `rain.record.graduated_credit` credits a record with the fees sunk in it, less the share
that returns as dividends. That share depends on how the holder discounts the future: at the lender's 5% it is
37.5%, so 62.5% of a fee is sunk. A ring that discounts less gets more of its fees back, has sunk less, and is
credited too much.

## Question

How patient does a ring have to be before the rule can be robbed, and what should a lender do about it?

Kind: deductive, checked by the strategy search of `graduation/`, with the ring's cash flows discounted at its
own rate.

## Setup

As `graduation/`, with two changes. The ring's present value is computed at its own discount rate `r_a` (5%,
4%, 3%, 2%, 1%, 0). And the lender's rule is run with the sunk share it would use if it assumed attackers
discount at no less than `r_low`: `r_low / (r_low + 0.03)`, which is 0.625, 0.4 and 0 for `r_low` = 5%, 2% and
0. Strategies: as before, defaulting on loan 1 to 151 (a patient ring may prefer to wait).

## Predictions (written 2026-11-19, before running)

1. **The rule as run in `graduation/` (sunk share 0.625) can be robbed by a ring that discounts at 3% or less,
   and not by one at 5%.** The switch is between 3.5% and 4.5%. The gain is small per unit washed (a few
   percent of the fees) and grows with the amount.
2. **Setting the sunk share for the most patient attacker allowed for is enough.** With the share for
   `r_low` = 2%, no strategy pays for a ring discounting at 2% or more. With a share of 0, none pays at any
   rate, including 0.
3. **The price is a slower graduation, not none.** With a sunk share of 0 the rule still raises each loan by
   the interest rate up to the evidence, which is the exit bound and needs no assumption about the ring. The
   newcomer of `graduation/` needs no guarantor after 44 cycles at a share of 0.625, 50 to 53 at 0.4, and 94
   to 96 at 0.

Failure would be: a profitable strategy against a sunk share of 0, or against the share for 2% from a ring at
2% or above.

## Scope

A ring that discounts at less than the rate at which lending earns is passing up that return, so very patient
rings are a stress test more than a forecast.
