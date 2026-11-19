# Vouching: a guarantor answers for a newcomer

Started 2026-11-19. Serves the question the last two experiments ended on: `collusion/` showed that a record
counts only along the reader's trust, and `first_loan/` that without a cost of identity nothing can be lent to
a stranger. Where can a newcomer start?

## The mechanism

`contracts/scripts/GuaranteedLoanScript.sol`. A guaranteed loan is two promises of the amount due: the
borrower's to the guarantor, and the guarantor's to the lender. The borrower's repayment goes straight to the
lender and keeps both. If the borrower defaults, the claim on them passes to the guarantor, who must pay the
lender or become the lender's defaulter. Both promisors pay the protocol fee.

So the lender relies on the guarantor's record. And on the log the borrower's kept promise is *to the
guarantor*, which is what a reader needs to know to weigh it.

## Questions

1. Can a guarantor and a ring of fake borrowers use guaranteed loans to manufacture records that rob the lender?
2. How much can a guarantor who burns their own standing take?
3. What does it cost a guarantor to vouch, and when is a vouch worth buying?

Kind: deductive. The simulation checks the formulas against the model of the contracts (which the tests check
against the contracts themselves).

## Decision it feeds

How the reference lender treats guaranteed loans: what counts against whose credit, and what a guaranteed
repayment says about the borrower.

## Setup

`Economy.current_rules` (fee 1%, minimum 0.1, point price 0.04, decay 0.03, discount rate 0.05), interest 5%,
in a large steady economy. The bank offers the largest amount due it believes will be repaid apart from shocks
(2% per loan): the rule `first_loan/` found a lender should use when thresholds have tail index 1. To a
stranger that is the floor, 100. Sam, the guarantor, has repaid 10,000 to the bank, so the bank will accept
10,000 due from Sam.

Arms:

| arm | what happens | the bank's rule |
|---|---|---|
| A | Sam guarantees a loan of 10,000 to each of `J` fake borrowers (1 or 5), who repay. Each then asks the bank for an unguaranteed loan and defaults. | naive: a repayment counts whoever it was made to. Sceptical: only promises made to the bank count. |
| B | Sam guarantees `J` fake borrowers at once (1, 5, 20). All default and Sam does not pay. | guarantees count against Sam's own credit, so they total at most 10,000. Control: they do not count. |
| C | Sam vouches for applicants of whom a share are opportunists. What does each vouch cost Sam, and what is it worth to a genuine borrower? | (no attack) |

Controls that must fail: in A the naive bank must be robbed, and in B the bank that does not count guarantees
against the guarantor must lose `J` times as much.

## Predictions (written 2026-11-19, before running)

1. **A naive bank is robbed through the guarantee, at a higher price than a plain wash.** Each fake borrower
   costs the ring 601 (the bank's interest, 476, and the net fees on two promises, 125) and then takes an
   unguaranteed 10,000. The ring gains 8,284 per fake borrower over what a stranger could take (within 1%),
   and Sam's credit is free again each time, so it scales with `J`.
2. **A sceptical bank loses nothing.** The fake borrower's kept promise was to Sam, so the bank offers them
   what it offers a stranger. The ring is 601 per fake borrower worse off than if it had not bothered.
3. **A guarantor can burn their standing once.** With guarantees counted against Sam's credit the bank loses
   one principal, 9,524, at every `J`: what Sam could have taken alone by borrowing and defaulting. Without
   that rule it loses `J` times 9,524.
4. **A vouch costs the guarantor their belief.** Sam's expected cost per vouch for 10,000 is the chance they
   end up paying, times the amount, plus the net fee: 262 if Sam is sure the applicant is genuine, 1,242 if
   Sam thinks there is a 10% chance they are an opportunist, 5,162 at 50% (simulated within two standard
   errors). A guarantor who vouches at a given price reveals what they believe.
5. **A vouch is worth buying only if the borrowed money earns more than shocks and fees cost.** At the fair
   price for a genuine borrower, the borrower comes out ahead when their surplus is above 3.41% of the
   principal per loan. At a 6% surplus a genuine newcomer nets 246 per loan with a guarantor against 5.1 on
   the stranger's loan of 100. At 3% the vouch costs more than it brings (-39).

Failure would be: any gain for the ring against the sceptical bank; a loss above one principal under the
counting rule; or the simulation disagreeing with a formula by more than 1%.

## Scope

The guarantor is permanent here. With thresholds of tail index 1 the bank never raises a loan, and a
guaranteed repayment tells the sceptical bank nothing about the borrower, so the borrower never graduates to
borrowing 10,000 alone. How a borrower should graduate is not answered. Sam's own standing is assumed, and so
is what Sam knows about applicants. Recovery from a defaulter by the guarantor (who holds the claim) is taken
as zero.
