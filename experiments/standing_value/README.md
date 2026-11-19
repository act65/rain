# What a default really costs

Started 2026-11-19. `default_frontier/` and `current_rules/` A reported how large a loan a *bond* can back,
which counts only the dividends on the points lost. That number is small, and misleading on its own: losing
standing costs more than dividends. This experiment does the fuller account.

## Question

Take a borrower climbing a ladder (each loan a fixed factor larger than the last, up to a cap), which is how
reputation would be used for credit in practice. If they default on loan number `n`, what do they lose, and
how much of it is dividends?

The account (`rain.ladder.ladder_default_account`):

    gain from default = amount kept
                        - dividends on the reputation destroyed (and on the reward forgone)
                        - access: the value of carrying on up the ladder, less the value of the best alternative
                        - anything else standing is worth (roles, services gated by reputation)

The alternative matters. If the defaulter is shut out for good, access is the whole future. If they can come
back as a new identity, it is only the difference between where they were on the ladder and the bottom of it.

Kind: deductive; the simulation checks the account against the model.

## Decision it feeds

How to describe what reputation is for, and what a lender should look at (the bond, or the borrower's place on
a ladder they would have to climb again).

## Setup

Current rules (`kappa` = 0.04, `delta` = 0.03, 1% fee with a 0.1 minimum), `r` = 0.05, 5% interest. Ladder: 100 DMD
growing 5% per loan to a cap of 5000 DMD (reached at loan 81), one loan per cycle, all reputation bonded each
time. Surplus per unit borrowed `sigma` = 1%, 3%, 6%. Two alternatives after a default: shut out for good, or
start again at once as a new identity at no cost. "Other" value is zero here; it subtracts one for one.

`run.py` computes the account at every rung, and checks it at five rungs by simulating both strategies in
`Economy` (repay and carry on; default, then the alternative) and comparing discounted money.

## Predictions (written 2026-11-19, before running)

1. The simulated gain from default agrees with the account within 0.5% of the amount kept, at every rung checked.
2. **The first rung is pure exposure** in every case: defaulting on loan 0 keeps about 105 DMD and loses under 15.
3. **With a 1% surplus, default pays at every rung**, whatever the alternative.
4. **With a 3% surplus**, while the ladder is growing there is a band of rungs in the middle where default does not
   pay, but it pays near the bottom (little yet to lose) and at the cap (nothing more to gain by staying, and
   3% a cycle on 5000 is worth less than 5250 now). I expect this with or without the option to start again,
   the band being narrower with it.
5. **With a 6% surplus**, default stops paying from some rung below 20 and never pays again, including at the cap,
   if the defaulter is shut out for good. If they can start again, it pays again at the cap.
6. **Dividends are a minority of the deterrent but not negligible**: at the cap they are between 10% and 30% of what
   a defaulter loses (3% surplus, shut out for good), and far less on the lower rungs.

Failure would be: the account disagreeing with the simulation, or dividends turning out to be most of the deterrent.

## Scope

One loan per cycle at the limit; a constant surplus rate; settlement after default is not modelled (the
defaulter never comes back as themselves). The numbers move with `sigma`, which is an input.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. account matches simulation within 0.5% of the amount kept | Held: worst error 0.31%, over 10 checks. |
| 2. the first rung is pure exposure in every case | **Wrong as stated.** True only when the defaulter can start again (they lose 9 to 20 DMD against 105 kept). If they are shut out for good and the surplus is 3% or more, the first loan is already safe: they would lose the whole ladder (235 DMD at a 3% surplus). |
| 3. 1% surplus: default pays everywhere | Held. |
| 4. 3% surplus: a safe band in the middle, unsafe at the bottom and at the cap, narrower with restart | Half right. Shut out for good: safe from rung 0 to 57, unsafe from there to the cap. Able to start again: safe only from rung 20 to 48. |
| 5. 6% surplus: safe from below rung 20 for good if shut out; unsafe again at the cap if able to start again | First part held (safe at every rung). **Second part wrong**: able to start again, default pays on rungs 0 to 4 and for the first 18 loans at the cap (rungs 81 to 98), and then stops paying. |
| 6. dividends between 10% and 30% of the loss at the cap, far less lower down | Held: 19% at the cap, 10% on first reaching it, 3% at rung 40, 1% at rung 10 (3% surplus, shut out). |

What this shows:

- **Access to future credit is most of what a default costs**, at every rung where staying is worth anything.
  A borrower on loan 40 (704 DMD) with a 3% surplus loses 35 DMD of dividends and 993 DMD of access.
- **Whether a defaulter can start again is the biggest single factor.** It decides whether the first loans are
  safe at all, and it shrinks the safe range at a 3% surplus from 58 rungs to 29. This is the identity
  question (Layer 2 in the blog post), and it is worth more than any parameter of the reputation rules.
- **Starting again costs exactly the climb.** Access lost by a defaulter who can come back is the gap between
  their rung and the bottom. That is why a ladder protects its upper rungs and not its lower ones, and why
  the first rungs need another form of security (a small size, a voucher, collateral).
- **A ladder stops protecting when it stops growing.** At the cap, staying is worth the surplus on a constant
  loan, and 3% a cycle on 5000 DMD (2344 DMD in present value) is less than the 5250 DMD to be had by leaving.
- **Dividends are small but can be decisive.** In the 6% case with restart, default pays on first reaching the cap
  (+153 DMD) and stops paying 18 loans later (-117 DMD). Nothing changes in between except that the borrower's
  reputation, earned at the cap's larger fees, has grown from 16,500 to 34,500 points, worth 270 DMD more in
  dividends. This is the job the dividend was designed for: making accumulated standing costly to throw away.
- **Any other value of standing subtracts one for one.** If good standing also gives access to something worth
  500 DMD in present value (a role, a service, another lender's ladder), default at any rung is 500 DMD less
  attractive. The account has a term for it; this experiment sets it to zero because it depends on what is
  built on the protocol.

Not settled: what `sigma` is for real borrowers, and settlement (a defaulter who pays the debt and returns as
themselves, which the model treats as never happening).

### Re-run after the payout fund was adopted (2026-11-19)

Unchanged, as expected for a steady-state account: the same safe rungs in all six cases and the same worst
error (0.31%). `results/SUMMARY.md` is from the re-run.
