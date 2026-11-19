# The first loan as the price of information

Started 2026-11-19. Serves the claim that a lender's rules can be derived from a belief, and replaces two
numbers that earlier experiments assumed: the 10% risk a lender accepts per loan, and the size of the first
loan to a stranger.

## Question

A lender who has never dealt with someone learns about them only by lending. What should it be willing to lose
on a first loan, how large should that loan be, and when should it raise the next one?

Kind: deductive. The closed forms are in `rain/ladder.py` (`repeat_value`, `stranger_value`,
`opportunist_share_bounds`, `growth_pays`, `identity_bound`). The run checks them two ways: a dynamic programme
that searches over every sequence of loan sizes, and a Monte Carlo simulation of borrowers.

## Decision it feeds

What the reference lender offers a stranger and how it sets its risk tolerance; what the post may say about
ladders.

## Model

A lender earns interest `i` = 5% on loans that are repaid and loses the principal otherwise; it discounts at
`r` = 5% per loan period. A borrower repays any amount up to a private threshold `c`, except that with
probability `q` = 2% per loan a shock makes them default. After a default the relationship is over.

Strangers are of two kinds. A share `pi0` are opportunists: they take the first loan, whatever its size, and
vanish. The rest are genuine, with thresholds Pareto distributed above a floor of 100 with tail index `a`
(`a` = 1 unless stated). A borrower has no use for more than `D` = 10,000.

The lender chooses the amount due on each loan knowing only the largest amount this borrower has repaid.

## Predictions (written 2026-11-19, before running)

1. **With `a` = 1 the lender never raises a loan.** The dynamic programme's best policy for a borrower who has
   repaid `M` is to lend `M` again, at every `M`. Raising the loan to `k M` keeps the expected amount repaid
   the same (the chance of repayment falls as `1 / k`) and puts more principal at risk.
2. **The first loan is the floor.** The best first amount due is 100 (within one grid step) for every
   opportunist share below 30.3%. Above 30.3% the best policy is not to lend to strangers.
3. **Between 2.8% and 30.3% opportunists the first loan is made at an expected loss.** At 10% it is expected to
   lose 7.0 and the relationship as a whole is worth +27.7; at 20%, 16.8 and +14.1 (within 2%). That loss is
   the price of information: what the lender pays to find out who is genuine.
4. **The simulation agrees with the formula** within 2% or two standard errors at shares of 0, 10%, 20%, 30%
   and 40%.
5. **The ladder assumed in earlier experiments loses money.** A lender who accepts a 10% chance of default on
   every loan (each loan 1.089 times the last) expects about -87 per stranger at a 10% opportunist share, where
   repeating the floor earns +27.7. A lender who requires every single loan to break even (the myopic rule)
   lends nothing to strangers once opportunists exceed 2.8%, and earns 0.
6. **Raising loans pays only when thresholds are heavy-tailed.** Far below `D`, the best policy raises the loan
   after a repayment exactly when `a` is below 0.30, 0.54 and 0.73 for interest of 5%, 10% and 20% (within
   0.03).
7. **With opportunists who can come back, the first loan is the price of an identity.** Let a new identity
   cost `C`, and let there be `m` opportunist applications for every genuine one whenever taking the loan and
   vanishing pays. It stops paying when the amount due is at most `C / (1 / 1.05 - 0.01)`, the identity bound.
   The lender's best first amount due, among the floor and the bound, is:

   | `m` | `C` = 0 | 20 | 60 | 120 |
   |---|---|---|---|---|
   | 0.25 | 100 (opportunists tolerated) | 100 | 63.7 | 100 (deterred) |
   | 1, 10 | no lending | 21.2 | 63.7 | 100 (deterred) |

   So with free identities and unlimited opportunists a stranger can be lent nothing.

Failure would be: a policy found by the dynamic programme that beats the predicted one by more than 1%; the
simulation disagreeing with the formulas; or a first loan above the identity bound surviving unlimited
opportunists.

## Scope

Borrowers are not strategic beyond the opportunists: a genuine borrower's threshold is given, not chosen.
Whether a borrower stays with a lender who never raises their loan is a separate question (`rain.ladder`'s
"stay" bound says growth of about 2% a loan is needed for a borrower to prefer staying, in a different model).
One lender, no competition. The floor, the tail index and the shock rate are assumed.
