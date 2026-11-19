# A borrower who chooses: joining the two models

Started 2026-11-19. Two models have been used side by side. In the *threshold* model a borrower repays any
amount up to a private threshold; `first_loan/` used it and found that a lender never raises a loan above
what a borrower has shown. In the *incentive* model a borrower weighs repaying against leaving;
`rain.ladder`'s "stay" bound came from it and says borrowers want loans to grow. This experiment derives the
first from the second.

## Model

A borrower can put `K` of borrowed money to use each period (their capacity; Pareto across borrowers). On
principal up to `K` they earn `sigma + i` per period, where `i` is the interest, so `sigma` is their net
return; beyond `K`, nothing. They pay the 1% fee, of which 37.5% returns as dividends if the promise is kept.
With probability 2% a period a shock takes the money and ends the relationship. They discount at 5%. Each
period they choose: repay, or keep the principal and be shut out.

## Predictions (written 2026-11-19, before running)

1. **Whether a borrower repays a loan that will simply be offered again depends on their return, not on the
   size of the loan.** Within capacity they repay when `sigma` is at least `sigma*` = 7.9% (within 0.2
   points), at a principal of 100 and of 10,000 alike. `rain.ladder.repay_surplus_threshold`. Roughly,
   `sigma*` is the discount rate plus the shock rate.
2. **The threshold is capacity, scaled.** Above capacity a borrower with `sigma` above `sigma*` keeps repaying
   up to a principal of `K (sigma + i) / (sigma* + i)` (within 1%, at `sigma` = 10%, 15%, 25%). Thresholds
   therefore have the tail of capacities, which is what the threshold model assumed.
3. **Opportunists are borrowers whose return is low.** Those with `sigma` below `sigma*` default on the first
   loan that has stopped growing. `first_loan/` took their share as given; it is the share of borrowers below
   `sigma*`.
4. **Growth holds them only while it lasts.** On the screening climb of `first_loan/` (from 43.6 by 5% a loan
   to 100, then 100 for ever), a borrower with `sigma` = 3% repays every loan of the climb and defaults on the
   first loan at 100. One with `sigma` = 0 defaults on the first loan of all. In cash, the lender's loss to the
   climber is the first loan, as to the other (within 2%): the interest received on the way up equals the
   growth of the loan.
5. **In gross terms the bar rises with the interest rate.** `sigma*` barely moves with `i` (7.7%, 7.9%, 8.2%
   at 2.5%, 5%, 10%), so the gross return a borrower needs, `sigma* + i`, rises about one for one: 10.2%,
   12.9%, 18.2%. A lender who raises its rate to cover losses turns more of its borrowers into defaulters.

Failure would be: a repay decision that depends on size within capacity, or thresholds not proportional to
capacity.

## Scope

A defaulter is shut out for good. With the option of starting again under a new identity the bar is higher
(`standing_value/`). The lender's policy is given, not a best response to these borrowers. Returns are constant
up to capacity and zero beyond it.
