# Collusion: results

Commit `e8b37fe` (dirty: False), 2026-11-19T14:57:25+00:00.

A stranger is offered 108.9 due; defaulting on it is worth 97.7 (present value).
Worst relative error, formula against simulation, over the attacks checked: 1.5e-05.

## A. What a wash costs

| amount | cost (simulated) | cost (formula) | share of the amount |
|---|---|---|---|
| 1,000 | 6.25 | 6.25 | 0.625% |
| 10,000 | 62.50 | 62.50 | 0.625% |
| 100,000 | 625.00 | 625.00 | 0.625% |

## B. A bank that believes the whole log (one confederate)

| washed | bank accepts (due) | attacker's profit | gain over a stranger, per unit washed |
|---|---|---|---|
| 1,000 | 1,089 | 971 | 0.873 |
| 10,000 | 10,889 | 9,710 | 0.961 |
| 100,000 | 108,889 | 97,103 | 0.970 |

## C. One confederate, the attacker's best amount

| bank's trust in unknown counterparties | best amount to wash | bank accepts, as a multiple of a stranger's | predicted multiple | gain over a stranger |
|---|---|---|---|---|
| 0.0 | 0 | 1.00 | 1.00 | 0.0 |
| 0.5 | 133 | 1.07 | 1.08 | 6.1 |
| 0.9 | 178 | 1.65 | 1.73 | 62.4 |
| 0.99 | 1,000 | 8.33 | 9.08 | 710.4 |
| 0.999 | 7,499 | 69.82 | 82.55 | 6,679.1 |

## D. Any number of confederates (up to 20), the attacker's best attack

| trust in unknown | confederates | amount washed with each | bank accepts, multiple of a stranger's | profit | multiple at n = 1, 2, 5, 10, 20 |
|---|---|---|---|---|---|
| 0.0 | 0 | 0 | 1.00 | 98 | 1.00, 1.00, 1.00, 1.00, 1.00 |
| 0.1 | 20 | 178 | 1.57 | 131 | 1.01, 1.02, 1.05, 1.14, 1.57 |
| 0.5 | 20 | 7,498,942 | 69,984.51 | 5,902,106 | 1.07, 1.23, 2.96, 69.94, 69,984.51 |
| 0.9 | 10 | 10,000,000 | 99,999.00 | 9,147,742 | 1.65, 8.33, 6,975.89, 99,999.00, 100,000.00 |

With trust 0.5 and the confederates known to be one group: best attack uses 1 confederate(s), washes 133, and the bank accepts 1.07 times a stranger's (profit 103.9).

## E. An honest borrower who repaid 10,000 to another real lender

| bank's trust in that lender | bank accepts (due) | share of what full trust gives | rungs of a 5% ladder still to climb |
|---|---|---|---|
| 0.0 | 108.9 | 1.0% | 94 |
| 0.5 | 109.0 | 1.0% | 94 |
| 0.9 | 109.8 | 1.0% | 94 |
| 0.99 | 119.4 | 1.1% | 92 |
| 0.999 | 972.2 | 8.9% | 50 |
| 1.0 | 10,888.9 | 100.0% | 0 |

## Control: an honest borrower climbing with the bank itself

- trust in unknown 0.0: offers 108.9, 118.6, 129.1, 140.6, 153.1, 166.7 (growth 1.0889 each)
- trust in unknown 0.5: offers 108.9, 118.6, 129.1, 140.6, 153.1, 166.7 (growth 1.0889 each)

## F. Added after the first run

One confederate, amount searched on a grid 50 times finer:

| trust in unknown | bank accepts, multiple of a stranger's | predicted multiple |
|---|---|---|
| 0.5 | 1.08 | 1.08 |
| 0.9 | 1.73 | 1.73 |
| 0.99 | 9.08 | 9.08 |
| 0.999 | 82.34 | 82.55 |

Confederates needed to bring the bank to 100 times a stranger's offer, each washing that amount:

| trust in unknown | confederates | cost of the washes | bank accepts, multiple of a stranger's | attacker's profit |
|---|---|---|---|---|
| 0.01 | 707 | 48,115 | 100.0 | -38,339 |
| 0.1 | 68 | 4,628 | 100.5 | 5,194 |
| 0.5 | 11 | 749 | 103.4 | 9,360 |
| 0.9 | 4 | 272 | 107.7 | 10,256 |

## G. Added after the first run: how much trust in unknown counterparties is safe

Free confederates, any number of them, any amount. Below the safe trust no ring gains anything.

| fee | safe trust in unknown counterparties | first-order estimate | best ring at 1.5 times the safe trust |
|---|---|---|---|
| 0.5% | 1.66% | 4.22% | 247 confederates washing 4,571 each: 42.0 times a stranger's offer, gain 502 |
| 1.0% | 3.32% | 8.44% | 123 confederates washing 4,786 each: 44.0 times a stranger's offer, gain 521 |
| 2.0% | 6.59% | 16.88% | 61 confederates washing 5,129 each: 47.1 times a stranger's offer, gain 550 |
| 5.0% | 16.15% | 42.21% | 24 confederates washing 6,918 each: 63.6 times a stranger's offer, gain 670 |
