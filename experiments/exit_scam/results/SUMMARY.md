# Exit scam: results

Commit `514658d` (dirty: False), 2026-11-19T13:25:26+00:00.

42 grid points; worst disagreement between simulation and formula 9.30e-08 (the simulation also pays the fee on each of the four defaulted loans, which the formula leaves out; it is added back for this comparison).

## Profit (DMD) from a 100-point identity, v = 0.3077 (demo)

Before the fees on the four defaulted loans (46.15 DMD in total, the same in every cell). n is the number of promises kept beforehand to buy reputation.

| lending ratio / v | n = 0 | n = 10 | n = 40 | more building |
|---|---|---|---|---|
| 0.50 | -15.38 | -92.31 | -323.08 | lowers profit |
| 1.00 | -0.00 | -38.46 | -153.85 | lowers profit |
| 1.25 | +7.69 | -11.54 | -69.23 | lowers profit |
| 1.50 | +15.38 | +15.38 | +15.38 | no effect |
| 2.00 | +30.77 | +69.23 | +184.62 | raises profit |
| 5.00 | +123.08 | +392.31 | +1200.00 | raises profit |
| 65.00 | +1969.23 | +6853.85 | +21507.69 | raises profit |

## The demo's lending ratio

- 1000 DMD against a 50-point bond is 20 DMD per point, 65 times the value of a point
- a 100-point identity extracts 1969 DMD; each extra kept promise adds 488 DMD

## What safe lending costs an honest user (lending ratio = v)

- a 1000 DMD credit line needs 3250 points, i.e. 130 kept promises
- at the keeper's fee those cost 1500 DMD
