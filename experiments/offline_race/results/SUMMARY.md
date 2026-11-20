# Offline, racing the news: results

Commit `e11d508` (dirty: False), 2026-11-20T10:31:22+00:00.

The take is in limits. Shops guess 5 places. Means over 20 seeds, with standard errors.

## A and B: nothing shared

| shops in the market | each accepts the limit / 5 | each accepts the limit / the market | ...and then accepts, of the limit |
|---|---|---|---|
| 100 | 20 | 1 | 1.0% |
| 1000 | 200 | 1 | 0.1% |

## C: gossip between shops

| swaps per shop per attacker's visit | 100 shops | 1,000 | 10,000 | rough prediction at 1,000 |
|---|---|---|---|---|
| 0.1 | 7.53 (0.16) | 11.88 (0.18) | 16.67 (0.19) | 14.82 |
| 0.3 | 3.42 (0.08) | 5.19 (0.07) | 6.91 (0.09) | 5.61 |
| 1.0 | 1.65 (0.04) | 2.34 (0.04) | 2.94 (0.05) | 2.38 |
| 3.0 | 1.06 (0.02) | 1.31 (0.02) | 1.59 (0.02) | 1.46 |

## D: through the chain

| carriers' delay, shops' sync rate | 100 shops | 1,000 | predicted |
|---|---|---|---|
| d=1, rho=1.0 | 1.32 (0.03) | 1.32 (0.03) | 1.32 |
| d=5, rho=0.2 | 2.91 (0.06) | 2.91 (0.06) | 2.90 |
| d=20, rho=0.05 | 8.92 (0.11) | 9.06 (0.11) | 8.90 |

## D': shops refuse when their last sync is older than 2 (d=5, rho=0.2, 1,000 shops)

Take 1.42 (0.04); largest in any run 1.80; cap 2.40. A shop is willing to deal 33% of the time.

## E: ten helpers (d=5, rho=0.2, 1,000 shops)

Take 21.12 (0.23); predicted 20.90.
