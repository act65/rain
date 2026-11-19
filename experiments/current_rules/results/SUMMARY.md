# The first four experiments under the current rules: results

Commit `1805efb` (dirty: True), 2026-11-19T12:36:26+00:00.

A point is worth v = 0.0150 DMD and costs 0.04 DMD.

## A. Largest safe loan

Worst relative error, formula against simulation, over 16 grid points: 1.1e-04.

| R | bond | sigma | P* formula | P* simulated | P* per point, in units of v |
|---|---|---|---|---|---|
| 500 | 100 | 0.0 | 2.893 | 2.893 | 0.386 |
| 500 | 100 | 0.005 | 2.893 | 2.893 | 0.386 |
| 500 | 100 | 0.02 | 2.893 | 2.893 | 0.386 |
| 500 | 100 | 0.045 | 10.818 | 10.818 | 1.442 |
| 500 | 500 | 0.0 | 7.179 | 7.179 | 0.957 |
| 500 | 500 | 0.005 | 7.179 | 7.179 | 0.957 |
| 500 | 500 | 0.02 | 9.649 | 9.649 | 1.286 |
| 500 | 500 | 0.045 | 27.045 | 27.047 | 3.606 |
| 5000 | 1000 | 0.0 | 15.773 | 15.774 | 0.210 |
| 5000 | 1000 | 0.005 | 15.773 | 15.774 | 0.210 |
| 5000 | 1000 | 0.02 | 21.227 | 21.227 | 0.283 |
| 5000 | 1000 | 0.045 | 59.500 | 59.495 | 0.793 |
| 5000 | 5000 | 0.0 | 71.697 | 71.697 | 0.956 |
| 5000 | 5000 | 0.005 | 71.697 | 71.697 | 0.956 |
| 5000 | 5000 | 0.02 | 96.486 | 96.486 | 1.286 |
| 5000 | 5000 | 0.045 | 270.453 | 270.449 | 3.606 |

- fees needed per unit of credit backed by a bond alone: 2.67 (i.e. 267 units of repaid loans at a 1% fee)
- surplus per loan above which access to future credit counts: 0.6563% of the principal
- the demo's second loan is 110 DMD; the largest safe loan for that borrower is 0.412 DMD (267 times smaller)
- control (worthless reputation): gain from defaulting P=1: +1.05, P=100: +105.00

## B. A lasting change in activity at cycle 300 (value of a point / its cost)

| arm | before | at the shock | peak | trough | 100 cycles later | cycles above 1 |
|---|---|---|---|---|---|---|
| x2 | 0.375 | 0.375 | 0.375 | 0.375 | 0.375 | 0 |
| x10 | 0.375 | 0.375 | 0.375 | 0.375 | 0.375 | 0 |
| /10 | 0.375 | 0.375 | 0.375 | 0.375 | 0.375 | 0 |
| x10 + farmer | 0.375 | 0.375 | 0.375 | 0.375 | 0.375 | 0 |

Farmer after the tenfold rise: 0 wash promises in cycles None to None after the shock; fees 0, dividends 0, profit +0 DMD. Honest holders' discounted dividends change by +0.0%.

## C. Exit scam: profit from 100 existing points plus points bought (DMD, before the fees on the defaulted loans)

Worst disagreement between simulation and formula: 9.5e-08.

| lending ratio / v | bought 0 | bought 250 | bought 1000 |
|---|---|---|---|
| 0.50 | -0.75 | -8.88 | -33.25 |
| 1.00 | -0.00 | -6.25 | -25.00 |
| 2.00 | +1.50 | -1.00 | -8.50 |
| 2.67 | +2.50 | +2.50 | +2.50 |
| 4.00 | +4.50 | +9.50 | +24.50 |
| 366.67 | +548.50 | +1913.50 | +6008.50 |

The demo lends 5.5 DMD per bonded point: 367 times v.

## D. Profit per identity (DMD): simulated (formula)

| identity | careful (0.9 v) | demo ratio (5.5) |
|---|---|---|
| none | -0.100 (-0.100) | -0.100 (-0.100) |
| bought | -2.750 (-2.750) | +540.500 (+540.500) |
| vouched | -0.250 (-0.250) | +543.000 (+543.000) |

| N bought identities | profit per identity | lenders' loss | sybil share of reputation at peak | honest dividend per point, next cycle |
|---|---|---|---|---|
| 1 | +545.0 | 550 | 0.001 | +0.2% |
| 10 | +545.0 | 5,500 | 0.012 | +1.5% |
| 100 | +545.0 | 55,000 | 0.107 | +15.0% |
| 1000 | +545.0 | 550,000 | 0.545 | +150.0% |
