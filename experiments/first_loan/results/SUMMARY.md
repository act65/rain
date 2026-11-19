# The first loan: results

Commit `e290e24` (dirty: False), 2026-11-19T15:12:29+00:00.

A borrower known to repay an amount is worth 0.414 per unit of it to the lender.
A first loan loses money in expectation above 2.8% opportunists; no lending to strangers above 30.3%.

## 1. A known borrower, tail index 1

Of 401 states, the best policy raises the loan in 0. Value per unit due 0.4143 (repeating: 0.4143).

## 2, 3. The first loan

| opportunist share | best first amount due | relationship value | formula | first loan alone | price of information |
|---|---|---|---|---|---|
| 0% | 100.0 | 41.43 | 41.43 | +2.76 | 0.00 |
| 10% | 5.0 | 34.45 | 27.76 | -7.04 | 7.04 |
| 20% | 5.0 | 30.09 | 14.10 | -16.84 | 16.84 |
| 30% | 5.0 | 25.73 | 0.43 | -26.64 | 26.64 |
| 31% | 5.0 | 25.30 | 0.00 | -27.62 | 27.62 |
| 40% | 5.0 | 21.38 | 0.00 | -36.44 | 36.44 |

## 4. Simulation of lending the floor repeatedly (400,000 strangers)

| opportunist share | simulated value | standard error | formula |
|---|---|---|---|
| 0% | 41.45 | 0.09 | 41.43 |
| 10% | 27.71 | 0.11 | 27.76 |
| 20% | 14.01 | 0.12 | 14.10 |
| 30% | 0.42 | 0.13 | 0.43 |
| 40% | -13.18 | 0.13 | -13.24 |

## 5. Policies compared, 10% opportunists (value per stranger)

| policy | value | standard error |
|---|---|---|
| repeat the floor | 27.7 | 0.1 |
| accept 10% risk on every loan (each 1.089 times the last) | -84.6 | 0.1 |
| double every loan | -408.8 | 1.4 |
| raise by the interest rate (1.05) | -32.1 | 0.1 |
| require every loan to break even (myopic) | 0.0 | 0.0 |

## 6. When raising the loan pays

| interest | largest tail index at which the best policy raises the loan | predicted | step at tail index 0.2 |
|---|---|---|---|
| 5% | 0.3 | 0.3 | 213.80 |
| 10% | 0.52 | 0.52 | 1230.27 |
| 20% | 0.72 | 0.72 | 3162.28 |

## 7. Opportunists who can come back: the best first amount due

| opportunist applications per genuine borrower | identity cost | identity bound | best first amount due | value per genuine borrower |
|---|---|---|---|---|
| 0.25 | 0 | 0.0 | 100.0 | 17.6 |
| 0.25 | 20 | 21.2 | 100.0 | 17.6 |
| 0.25 | 60 | 63.7 | 63.6 | 26.3 |
| 0.25 | 120 | 127.3 | 100.0 | 41.4 |
| 1.0 | 0 | 0.0 | 0.0 | 0.0 |
| 1.0 | 20 | 21.2 | 21.2 | 8.8 |
| 1.0 | 60 | 63.7 | 63.6 | 26.3 |
| 1.0 | 120 | 127.3 | 100.0 | 41.4 |
| 10.0 | 0 | 0.0 | 0.0 | 0.0 |
| 10.0 | 20 | 21.2 | 21.2 | 8.8 |
| 10.0 | 60 | 63.7 | 63.6 | 26.3 |
| 10.0 | 120 | 127.3 | 100.0 | 41.4 |
