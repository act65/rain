# Would a lender let the guarantor go?

Started 2026-11-19. `graduation/` showed that a lender *can* replace a guarantee with unsecured credit
without being robbed. It did not show that a lender would want to: with a guarantee the guarantor carries the
risk that a shock stops the borrower repaying, and without one the lender does.

## Question

At what interest rate on the unsecured part is a lender willing to let the guarantee shrink, is the borrower
still better off, and how fast does the borrower then graduate?

Kind: deductive. Checked by simulating borrowers with shocks along the graduation path.

## Setup

As `graduation/`: a newcomer borrows 10,000 a cycle in total (amount due), the lender offers unsecured what
`rain.record.graduated_credit` allows, and the rest is guaranteed. Interest on guaranteed loans is 5%. Shocks
2% per cycle: the borrower then repays nothing, the guarantor pays the guaranteed part, and the lender loses
the unsecured principal. The lender's interest is its margin, as in `first_loan/`. The guarantor charges its
expected cost: 2% of the guaranteed amount plus the fee it sinks.

Three arrangements: (a) guaranteed for ever; (b) graduating, unsecured at the same 5%; (c) graduating,
unsecured at a rate `i_u` that pays the lender for the risk.

## Predictions (written 2026-11-19, before running)

1. **At equal interest the lender prefers the guarantee.** Its expected present value from the newcomer under
   (b) is lower than under (a), by between 5% and 25%.
2. **A premium of 2.14 points makes the lender indifferent.** With `i_u = (i + q) / (1 - q)` = 7.14%, (c) is
   worth the same to the lender as (a), within 1% (simulated within two standard errors).
3. **The borrower still gains.** A guarantee costs the borrower 7.76% of the principal per loan in interest
   and the guarantor's price; unsecured at 7.14% it is cheaper by 55 to 62 per cycle on 10,000 once
   graduated. The saving is the guarantor's fee, which nobody has to sink any more. So there is a range of
   unsecured rates, 7.14% to 7.76%, at which both the lender and the borrower prefer to graduate.
4. **A higher rate graduates faster.** The growth allowed by the exit bound is `1 + i_u`. At 7.14% the
   guarantee is gone after 34 to 36 cycles, against 44 at 5%.

Failure would be: no rate at which both sides prefer graduation.

## Scope

One lender. With competing lenders the unsecured rate would be pushed towards the lower end of the range; a
single lender could ask for the top of it. The guarantor's price is its cost, with no margin.
