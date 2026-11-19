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

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. with `a` = 1 the lender never raises a loan | Held: the best policy raises the loan in 0 of 401 states, and its value is the repeat value, 0.414 per unit due. |
| 2. the first loan is the floor; no lending above 30.3% opportunists | **Wrong.** The search found a better policy: make the first loan as small as allowed (5, the smallest I let it try), then lend the floor. A tiny loan screens out opportunists almost for nothing, because I had them take the first loan *whatever its size*. That policy is worth 34.5 per stranger at a 10% share where starting at the floor is worth 27.8, and it stays profitable at any share. My formula only covered policies that repeat the first amount. |
| 3. first loan made at an expected loss between 2.8% and 30.3% | The numbers held for the policy they describe (lend the floor, then repeat): -7.04 and +27.76 at 10%, -16.84 and +14.10 at 20%. Given the outcome of 2, that policy is not the best one. |
| 4. simulation agrees with the formula | Held at all five shares, within two standard errors. |
| 5. the 10%-risk ladder loses money; the myopic lender earns nothing | Held: -84.6 per stranger against +27.7 for repeating the floor. Raising by 5% a loan from the floor loses 32; doubling loses 409. |
| 6. raising pays only for tail index below 0.30, 0.54, 0.73 | Held: 0.30, 0.52, 0.72. When it does pay, the steps are large (hundreds of times at tail index 0.2). |
| 7. with returning opportunists the first loan is the identity bound | Held in every cell, searching over all first amounts and not only the two I named. With free identities and at least as many opportunists as genuine borrowers, nothing is lent. |

The failure of 2 is a gap in the model, not a result about lending. An opportunist who would repay a loan of
5 in order to be offered 100 is not screened by the small loan. `rain.ladder`'s exit bound says when climbing
in order to default stops paying: when each loan is at most `1 + i` times the last. So the question has to be
asked with that constraint on the lender.

## Follow-up: the lender may raise a loan by at most the interest rate (2026-11-19)

Same model, with one constraint: each amount due is at most 1.05 times the largest this borrower has repaid,
from the first loan on. Then an opportunist gains nothing by repaying in order to default later, and taking
the first loan is their best move, as assumed. The grid now extends below the floor.

Predictions (written before this run):

8. **The first loan is below the floor, and smaller the more opportunists there are**: between 80 and 95 at a
   10% share, 50 and 70 at 20%, 35 and 60 at 30%. After it the best policy raises the loan by the full 5% each
   time until the floor, and never after. Lending to strangers stays worthwhile until about 59% opportunists
   (57% to 61%), far above the 30.3% of the repeat-only policy.
9. **With returning opportunists, the ladder starts at the price of an identity.** Unlimited opportunists and
   an identity cost of 20 or 60: the lender starts at the identity bound (21.2 or 63.7) and climbs to the
   floor, worth 18.5 and 36.9 per genuine borrower (within 5%), against 8.8 and 26.3 for repeating the bound.
10. **A simulation of the best policy at a 30% share agrees with the dynamic programme** within 2% or two
    standard errors.

### Outcome of the follow-up (2026-11-19)

| prediction | outcome |
|---|---|
| 8. first loan below the floor, smaller with more opportunists; raise by 5% to the floor and never after; lending until about 59% | Held: 86.4, 64.5 and 43.6 at shares of 10%, 20% and 30%. The best step is 1.050 everywhere below the floor and 1.000 everywhere at or above it. Strangers are still lent to at 55% and not at 58%. The limit as the first loan shrinks is 59.2%; the smallest loan on the grid is 1, which is why it stops a little earlier. |
| 9. with returning opportunists, start at the identity bound and climb: 18.5 and 36.9 | Held: 18.5 and 36.8, against 8.8 and 26.2 for repeating the bound. |
| 10. simulation agrees with the programme | Held: 8.79 (standard error 0.08) against 8.77. |

What this shows:

- **The first loan is a purchase of information, and its size is the lender's choice of how much to buy.**
  At a 20% opportunist share the best first loan is 64.5 and is expected to lose 10.9 by itself; the
  relationships it starts make the stranger worth +17.4. A lender who requires every loan to break even lends
  nothing and earns nothing.
- **A ladder below the floor, and none above it.** Below the amount every genuine borrower is good for, the
  lender raises each loan as fast as the exit bound allows, to recover the floor it gave up for screening.
  Above it, with thresholds of tail index 1, it never raises a loan: the expected amount repaid does not
  grow with the amount lent, and the principal at risk does. Growth above the floor pays only with a much
  heavier tail (index below 0.30 at 5% interest).
- **The 10%-risk ladder of the earlier experiments is not something a lender would run at 5% interest.** It
  loses 85 per stranger. The risk a lender can accept per loan is set by its margin and by what a survivor is
  worth, not chosen freely. `standing_value/` and `collusion/` used that ladder as the lender's rule; their
  conclusions are about the borrower's and the attacker's side and do not depend on the lender profiting, but
  the lender's side of them should be re-read with this in mind.
- **Where opportunists can return, the first rung is the price of an identity.** Above it they flood in;
  at or below it they stay away, and the ladder climbs from there. With free identities nothing can be lent
  to a stranger at all. This is the same conclusion as `collusion/` from the other side: without a cost of
  identity, or someone who will answer for the newcomer, there is nowhere to start.

What it does not show: why a borrower would stay with a lender who never raises their loan; what competition
between lenders does to the first loan (a rival could wait and poach the survivors, which removes the reason to
pay for the information); or what the floor and the tail index are for real borrowers.
