# Offline, an allowance backed by locked funds: results

Commit `4c3a648` (dirty: False), 2026-11-20T11:06:14+00:00.

Amounts are in units of the allowance. 1,000 shops, each accepting a fifth; a note reaches the chain after 5; a shop syncs 0.2 times per unit of time. Means over 20 seeds, standard errors in brackets.

| | alone | ten helpers |
|---|---|---|
| taken, with a certificate | 2.91 (0.06) | 21.12 (0.23) |
| taken, without one | 2.91 (0.06) (the same run by run: True) | |
| formula | 2.90 | 20.90 |
| taken when the certificate lasts 10 | 2.00 (0.00) | 17.07 (0.12) |
| reachable in that time | 2.00 | 20.00 |

Shops' loss to an attacker alone: 2.94 (0.06) with plain notes, 1.94 (0.06) with locked funds (fees of 1% included).

Notes left unpaid by payers who stay within the allowance, 2% of whom lose everything else: 0.00% with locked funds, 2.60% with plain notes.

| float, in allowances | attacker's gain alone | with ten helpers |
|---|---|---|
| 0 | +1.91 | +20.12 |
| 1 | +0.91 | +19.12 |
| 2 | -0.09 | +18.12 |
| 5 | -3.09 | +15.12 |

A shop that says an honest payer has overspent: after 14 units of time 95.5% of shops that believe hearsay refuse the payer, and 0% of shops that act only on notes they can check.
