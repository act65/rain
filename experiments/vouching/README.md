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

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`. All five predictions held, and the formulas match the simulation to
1e-8. (The first run reported everything 37.5 too high: the dividends Sam collects anyway on the loan that
gave them their standing. The results are now net of that.) Both controls failed as they should.

| prediction | outcome |
|---|---|
| 1. a naive bank is robbed: 8,284 per fake borrower | Held: +8,284 each, with 1 or 5 of them. |
| 2. a sceptical bank loses nothing; the ring is 601 worse off per fake borrower | Held: -601 each. The bank is 381 ahead per fake borrower: the interest on the guaranteed loan, less the stranger's loan it loses. |
| 3. a guarantor can burn their standing once | Held: the bank loses 9,524 with 1, 5 or 20 fake borrowers when guarantees count against the guarantor's credit, and 9,524 times their number when they do not. |
| 4. a vouch costs the guarantor their belief: 262, 1,242, 5,162 | Held: 261.2, 1,241.3 and 5,158.6 simulated, each within two standard errors. A vouch that goes wrong costs the guarantor 10,062.5 in the model; the bank is paid in full. |
| 5. a vouch is worth buying above a 3.41% surplus | Held: -39 per loan at 3%, about zero at 3.41%, +246 at 6% (against +5 for the stranger's loan of 100). |

What this shows:

- **A guarantee is the answer to "where can a newcomer start?"** The lender needs no belief about the
  newcomer. It needs one about the guarantor, and it has one. The newcomer borrows 10,000 on the first day
  where a stranger gets 100.
- **Two rules make it safe, and both follow from reading the record as evidence.** Count a guarantee against
  the guarantor's own credit, since it is their promise: then a guarantor can lose the lender no more than
  they could alone. And give a guaranteed repayment no weight as evidence about the borrower, since that
  promise was made to the guarantor, who may be a confederate: `rain.record.weigh` does this without being
  told, for any reader who trusts only its own dealings.
- **A guarantor's price is their belief made visible.** The guarantor pays when the borrower does not, so the
  least they can charge is their own estimate of that chance. This is the sense in which vouching is evidence:
  the lender does not have to estimate how good the guarantor's judgement is, because the guarantor bears the
  cost of being wrong.
- **Faking through a guarantee costs fifteen times more than a plain wash** (6.0% of the amount against
  0.625%), because the loan is real and the bank is paid interest on it. It still pays against a bank that
  counts it.

What it does not show, and what is now the open question: **graduation.** A sceptical bank learns nothing
about the borrower from guaranteed loans, and with thresholds of tail index 1 it never raises a loan of its
own. So in this model the newcomer needs the guarantor for ever. Something has to let a record made under a
guarantee count for a little: the interest paid to the bank is a real cost, 4.8% of each loan, and that is
evidence of a kind that a wash is not. That needs a belief in which paying to appear reliable is itself
informative, which is the "fees as the cost of faking" direction and has not been derived.
