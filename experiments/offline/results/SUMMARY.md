# Offline: results

Commit `c96370a` (dirty: False), 2026-11-20T06:25:19+00:00.

A payer who has shown 1,000 has a limit of 1,088.9; a stranger, 108.9.

## A. each payee accepts the whole limit

| payees (or hubs) | each accepts | owed in all, as a multiple of the limit | default rate | predicted | an attacker takes (limits) |
|---|---|---|---|---|---|
| 1 | 1,088.9 | 1.00 | 9.97% (se 0.02) | 10.00% | 1.00 |
| 2 | 1,088.9 | 2.00 | 55.00% (se 0.02) | 55.00% | 2.00 |
| 5 | 1,088.9 | 5.00 | 81.93% (se 0.05) | 82.00% | 5.00 |
| 10 | 1,088.9 | 10.00 | 90.93% (se 0.04) | 91.00% | 10.00 |

## B. each accepts the limit / 5

| payees (or hubs) | each accepts | owed in all, as a multiple of the limit | default rate | predicted | an attacker takes (limits) |
|---|---|---|---|---|---|
| 1 | 217.8 | 0.20 | 1.98% (se 0.01) | 2.00% | 0.20 |
| 2 | 217.8 | 0.40 | 1.98% (se 0.01) | 2.00% | 0.40 |
| 4 | 217.8 | 0.80 | 1.98% (se 0.01) | 2.00% | 0.80 |
| 5 | 217.8 | 1.00 | 9.97% (se 0.02) | 10.00% | 1.00 |
| 10 | 217.8 | 2.00 | 55.00% (se 0.02) | 55.00% | 2.00 |

## C. hubs, each allowing the whole limit in all

| payees (or hubs) | each accepts | owed in all, as a multiple of the limit | default rate | predicted | an attacker takes (limits) |
|---|---|---|---|---|---|
| 1 | 1,088.9 | 1.00 | 9.97% (se 0.02) | 10.00% | 1.00 |
| 2 | 1,088.9 | 2.00 | 55.00% (se 0.02) | 55.00% | 2.00 |
| 5 | 1,088.9 | 5.00 | 81.93% (se 0.05) | 82.00% | 5.00 |

## S. A payer who has already defaulted on the chain

| case | taken in all (limits) |
|---|---|
| 1 payees, log stale | 1.20 |
| 5 payees, log stale | 2.00 |
| 5 payees, log fresh | 1.00 |
| 5 payees, limit / 6 (the lender counted as a place) | 1.00 |

## Growth of an honest payer's limit over 30 windows

| case | limit at the start | after | growth per window (last ten) | first step |
|---|---|---|---|---|
| default reading, 1 payee | 108.9 | 1,401.2 | 1.0889 | 1.0889 |
| default reading, 5 of 5 payees | 108.9 | 108.9 | 1.0000 | 1.0000 |
| concurrent, 5 of 5, payees trust each other fully | 108.9 | 1,401.2 | 1.0889 | 1.0889 |
| concurrent, 4 of 5, full trust | 108.9 | 108.9 | 1.0000 | 1.0000 |
| concurrent, 5 of 5, trust 0.9 | 108.9 | 126.1 | 1.0000 | 1.0566 |
| concurrent, 5 of 5, trust 0.5 | 108.9 | 109.5 | 1.0000 | 1.0051 |
| concurrent, 2 of 2, trust 0.9 | 108.9 | 188.4 | 1.0014 | 1.0793 |
| one hub, spent at 5 payees | 108.9 | 1,401.2 | 1.0889 | 1.0889 |
| one hub, spent at 2 payees | 108.9 | 1,401.2 | 1.0889 | 1.0889 |

## Washing with notes issued at once: the largest offer extracted, as a multiple of a stranger's

| the bank's trust in unknown counterparties | default reading, 1 confederate | concurrent, 1 confederates sharing the amount | concurrent, 2 confederates sharing the amount | concurrent, 5 confederates sharing the amount | concurrent, 2 confederates, the amount each | concurrent, 5 confederates, the amount each | default reading, 5 confederates, the amount each |
|---|---|---|---|---|---|---|---|
| 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.5 | 1.08 | 1.08 | 1.06 | 1.06 | 1.06 | 1.06 | 3.53 |
| 0.9 | 1.73 | 1.73 | 1.40 | 1.24 | 1.40 | 1.24 | 8,140.11 |
