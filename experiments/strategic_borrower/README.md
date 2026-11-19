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

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`. The expected values behind them were computed by direct summation and
agree with a simulation of shock times within two standard errors.

| prediction | outcome |
|---|---|
| 1. repaying depends on the return, not the size; `sigma*` = 7.9% | Held: 7.89% from the formula, and from comparing the two strategies at a principal of 100 and of 10,000. |
| 2. the threshold is capacity times `(sigma + i) / (sigma* + i)` | Held: 1.164, 1.552 and 2.328 times capacity at returns of 10%, 15% and 25%, found and by formula. |
| 3. opportunists are borrowers with a return below `sigma*` | This is how the model defines them, given 1; nothing separate was measured. |
| 4. on the screening climb a borrower with a 3% return repays the climb and defaults at 100; the lender loses the first loan in cash | Held in substance. They default on loan 18 of 19, not 19: as I built the ladder the eighteenth loan is 99.9 and the next is 100, so growth has already stopped at 18. The lender's cash from them is -41.5, exactly the first principal. A borrower with no return, or 1%, defaults on the first loan; at 10% they never default. |
| 5. the net return needed barely moves with the interest rate; the gross return rises one for one | Held: 7.75%, 7.89%, 8.17% net and 10.2%, 12.9%, 18.2% gross at interest of 2.5%, 5% and 10%. |

What this shows:

- **The two models are one.** The threshold of the threshold model is capacity scaled by a factor that
  depends on the borrower's return, so it inherits the tail of capacities. Nothing in `first_loan/`,
  `collusion/` or `vouching/` needs changing.
- **A relationship enforces itself when the borrower's net return per loan exceeds about their discount rate
  plus the chance the relationship ends anyway** (7% here; 7.9% with fees and interest on the principal at
  risk). Below that, only growth keeps them, and only while it lasts.
- **There was no conflict between "borrowers want growth" and "lenders never raise".** Growth retains
  low-return borrowers until it stops, and then they default. A lender has no reason to want them. Loans grow
  during the screening climb and nowhere else.
- **The share of opportunists is not a free input.** It is the share of applicants whose return is below
  `sigma*`. The borrowers assumed in the earlier experiments (returns of 3% and 6%) are all below it, which
  is the same finding as `standing_value/`: they default when the ladder reaches its cap.
- **Raising the interest rate does not help the lender with them.** The return a borrower needs rises with
  the rate, so a higher rate turns more borrowers into defaulters.

What it does not show: borrowers who can start again under a new identity, a lender choosing its policy
against these borrowers, or returns that fall gradually with the amount instead of stopping at a capacity.
