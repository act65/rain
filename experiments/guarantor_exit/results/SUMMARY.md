# Would a lender let the guarantor go? Results

Commit `723a2bd` (dirty: False), 2026-11-19T16:30:13+00:00.

| arrangement | lender's expected value | simulated | standard error | relative to (a) | guarantee gone in cycle | borrower's cost per cycle, at cycle 100 |
|---|---|---|---|---|---|---|
| a. guaranteed for ever | 7,143 | 7,136 | 5 | 1.000 | never | 738.7 |
| b. graduating, unsecured at 5% | 6,565 | 6,561 | 5 | 0.919 | 44 | 476.2 |
| c. graduating, unsecured at 7.14% | 7,114 | 7,112 | 5 | 0.996 | 35 | 666.7 |

The lender is indifferent at an unsecured rate of 7.14%. A guarantee costs the borrower 7.76% of the principal per loan; a graduated borrower pays as much at an unsecured rate of 7.98%.

Cycle in which the guarantee is gone, by unsecured rate: 5.00%: 44, 6.00%: 39, 7.14%: 35, 7.98%: 33.
