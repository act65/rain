# A borrower who chooses: results

Commit `723a2bd` (dirty: False), 2026-11-19T16:30:12+00:00.

## 1. The return at which a borrower repays a loan that will be offered again

Formula: 7.89%. Found by comparing the two strategies: 7.89% at a principal of 100, 7.89% at 10,000. Discount rate plus shock rate: 7%.

Value of always repaying (principal 1,000), by summation and by simulating shock times:

| net return | summation | simulated | standard error |
|---|---|---|---|
| 3.0% | 365.4 | 365.1 | 0.2 |
| 7.9% | 1,100.4 | 1,099.3 | 0.7 |
| 15.0% | 2,165.4 | 2,163.3 | 1.3 |

## 2. Above capacity: the largest principal still repaid, over capacity

| net return | found | formula |
|---|---|---|
| 10% | 1.164 | 1.164 |
| 15% | 1.552 | 1.552 |
| 25% | 2.328 | 2.328 |

## 4. The screening climb (43.6 rising 5% a loan to 100, then 100 for ever)

| net return | defaults on loan | lender's cash from this borrower | first principal |
|---|---|---|---|
| 0% | 1 of 19 | -41.5 | 41.5 |
| 1% | 1 of 19 | -41.5 | 41.5 |
| 3% | 18 of 19 | -41.5 | 41.5 |
| 6% | 18 of 19 | -41.5 | 41.5 |
| 10% | never | - | 41.5 |

## 5. By interest rate

| interest | net return needed (formula) | found | gross return needed |
|---|---|---|---|
| 2.5% | 7.75% | 7.75% | 10.2% |
| 5.0% | 7.89% | 7.89% | 12.9% |
| 10.0% | 8.17% | 8.17% | 18.2% |
