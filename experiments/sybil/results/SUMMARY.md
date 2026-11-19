# Sybil identities: results

Commit `1805efb` (dirty: True), 2026-11-19T12:36:09+00:00.

## Profit per 100-point identity (DMD), v = 0.3077

| scenario | naive (20 per point): simulated (formula) | careful (0.9 v per point): simulated (formula) |
|---|---|---|
| S1_free_mint | +1988.46 (+1988.46) | +16.15 (+16.15) |
| S2_bought | +1942.31 (+1942.31) | -30.00 (-30.00) |
| S3_vouched | +1957.69 (+1957.69) | -14.62 (-14.62) |

Holding a free-minted identity instead of attacking with it is worth 30.77 DMD in dividends.

## Scaling: N bought identities attacking a running economy in one cycle

| lender | N | fee per promise | cost of 100 points | lent per point | profit per identity | lenders' loss | sybil share of reputation at peak | honest dividend per point, next cycle |
|---|---|---|---|---|---|---|---|---|
| naive | 1 | 2.97e-04 | 1.19e-03 | 20 | +2000 | 2000 | 0.001 | +0.01% |
| naive | 10 | 2.97e-04 | 1.19e-03 | 20 | +2000 | 2e+04 | 0.007 | +0.11% |
| naive | 100 | 2.97e-04 | 1.19e-03 | 20 | +2000 | 2e+05 | 0.068 | +1.11% |
| naive | 1000 | 2.97e-04 | 1.19e-03 | 20 | +2000 | 2e+06 | 0.421 | +11.06% |
| careful | 1 | 2.97e-04 | 1.19e-03 | 7.03e-06 | -0.000783 | 0.000703 | 0.001 | +0.01% |
| careful | 10 | 2.97e-04 | 1.19e-03 | 6.99e-06 | -0.000787 | 0.00699 | 0.007 | +0.11% |
| careful | 100 | 2.97e-04 | 1.19e-03 | 6.62e-06 | -0.0008245 | 0.06616 | 0.068 | +1.11% |
| careful | 1000 | 2.97e-04 | 1.19e-03 | 4.43e-06 | -0.001043 | 0.4433 | 0.421 | +11.06% |
