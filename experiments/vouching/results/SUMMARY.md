# Vouching: results

Commit `fcb6e5b` (dirty: False), 2026-11-19T15:23:16+00:00.

A stranger is offered 100.0 due; defaulting on it is worth 89.8.
Worst relative error, formula against simulation, in arm A: 9.9e-09.

## A. Fake borrowers who repay a guaranteed loan, then borrow alone and default

| fake borrowers | bank | bank then offers each | ring's gain per fake borrower, over a stranger's | bank's loss |
|---|---|---|---|---|
| 1 | naive | 10,000 | +8,284 | 9,048 |
| 1 | sceptical | 100 | -601 | -381 |
| 5 | naive | 10,000 | +8,284 | 45,238 |
| 5 | sceptical | 100 | -601 | -1,905 |

## B. The guarantor lets every guaranteed loan default and does not pay

| fake borrowers | guarantees count against the guarantor's credit | loans made | bank's loss | ring's present value |
|---|---|---|---|---|
| 1 | yes | 1 | 9,524 | 9,324 |
| 1 | no (control) | 1 | 9,524 | 9,324 |
| 5 | yes | 1 | 9,524 | 9,324 |
| 5 | no (control) | 5 | 47,619 | 46,619 |
| 20 | yes | 1 | 9,524 | 9,324 |
| 20 | no (control) | 20 | 190,476 | 186,476 |

## C. What a vouch for 10,000 costs the guarantor

| share of applicants who are opportunists | expected cost (formula) | simulated | standard error |
|---|---|---|---|
| 0% | 262.5 | 261.2 | 1.0 |
| 10% | 1,242.5 | 1,241.3 | 2.3 |
| 50% | 5,162.5 | 5,158.6 | 3.5 |

One vouch that goes wrong, in the model: the guarantor is out 10,062.5 and the bank loses -476.2.

A genuine borrower, paying the fair price of 262.5 per loan (worth buying above a surplus of 3.41%):

| surplus per loan | net per loan with a guarantor (10,000) | net per loan alone (100) |
|---|---|---|
| 3.00% | -39.3 | +2.23 |
| 3.41% | -0.2 | +2.62 |
| 6.00% | +246.4 | +5.09 |
