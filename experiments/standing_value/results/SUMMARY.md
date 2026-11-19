# What a default really costs: results

Commit `8770db0` (dirty: False), 2026-11-19T14:49:12+00:00.

Account against simulation (3% surplus): worst error 3.1e-03 of the amount kept, over 10 checks.

## Where default pays

| case | rungs where default does NOT pay (of 0 to 120) | pays at the cap? |
|---|---|---|
| sigma=0.01, shut out for good | none | yes |
| sigma=0.01, can start again | none | yes |
| sigma=0.03, shut out for good | 0 to 57 (58 rungs) | yes |
| sigma=0.03, can start again | 20 to 48 (29 rungs) | yes |
| sigma=0.06, shut out for good | 0 to 120 (121 rungs) | no |
| sigma=0.06, can start again | 5 to 120 (98 rungs) | no |

## The account at selected rungs (DMD)

| case | rung | loan | kept by defaulting | reputation held | dividends lost | access lost | gain from default | dividends as share of the loss |
|---|---|---|---|---|---|---|---|---|
| sigma=0.01, shut out for good | 0 | 100 | 105 | 0 | 0.4 | 34.4 | +70.2 | 1% |
| sigma=0.01, shut out for good | 10 | 163 | 171 | 284 | 4.9 | 50.5 | +115.6 | 9% |
| sigma=0.01, shut out for good | 20 | 265 | 279 | 671 | 11.1 | 73.1 | +194.4 | 13% |
| sigma=0.01, shut out for good | 40 | 704 | 739 | 2147 | 35.0 | 145.6 | +558.6 | 19% |
| sigma=0.01, shut out for good | 60 | 1868 | 1961 | 5894 | 95.8 | 258.0 | +1607.6 | 27% |
| sigma=0.01, shut out for good | 81 | 5000 | 5250 | 16536 | 267.7 | 343.7 | +4638.5 | 44% |
| sigma=0.01, shut out for good | 120 | 5000 | 5250 | 34541 | 537.8 | 343.7 | +4368.4 | 61% |
| sigma=0.01, can start again | 0 | 100 | 105 | 0 | 0.4 | 1.3 | +103.3 | 23% |
| sigma=0.01, can start again | 10 | 163 | 171 | 284 | 4.9 | 17.4 | +148.8 | 22% |
| sigma=0.01, can start again | 20 | 265 | 279 | 671 | 11.1 | 40.0 | +227.5 | 22% |
| sigma=0.01, can start again | 40 | 704 | 739 | 2147 | 35.0 | 112.5 | +591.7 | 24% |
| sigma=0.01, can start again | 60 | 1868 | 1961 | 5894 | 95.8 | 224.9 | +1640.7 | 30% |
| sigma=0.01, can start again | 81 | 5000 | 5250 | 16536 | 267.7 | 310.6 | +4671.6 | 46% |
| sigma=0.01, can start again | 120 | 5000 | 5250 | 34541 | 537.8 | 310.6 | +4401.6 | 63% |
| sigma=0.03, shut out for good | 0 | 100 | 105 | 0 | 0.4 | 234.8 | -130.2 | 0% |
| sigma=0.03, shut out for good | 10 | 163 | 171 | 284 | 4.9 | 344.3 | -178.1 | 1% |
| sigma=0.03, shut out for good | 20 | 265 | 279 | 671 | 11.1 | 498.6 | -231.1 | 2% |
| sigma=0.03, shut out for good | 40 | 704 | 739 | 2147 | 35.0 | 992.9 | -288.7 | 3% |
| sigma=0.03, shut out for good | 60 | 1868 | 1961 | 5894 | 95.8 | 1758.9 | +106.6 | 5% |
| sigma=0.03, shut out for good | 81 | 5000 | 5250 | 16536 | 267.7 | 2343.7 | +2638.5 | 10% |
| sigma=0.03, shut out for good | 120 | 5000 | 5250 | 34541 | 537.8 | 2343.7 | +2368.4 | 19% |
| sigma=0.03, can start again | 0 | 100 | 105 | 0 | 0.4 | 8.9 | +95.7 | 4% |
| sigma=0.03, can start again | 10 | 163 | 171 | 284 | 4.9 | 118.4 | +47.7 | 4% |
| sigma=0.03, can start again | 20 | 265 | 279 | 671 | 11.1 | 272.8 | -5.3 | 4% |
| sigma=0.03, can start again | 40 | 704 | 739 | 2147 | 35.0 | 767.1 | -62.8 | 4% |
| sigma=0.03, can start again | 60 | 1868 | 1961 | 5894 | 95.8 | 1533.1 | +332.5 | 6% |
| sigma=0.03, can start again | 81 | 5000 | 5250 | 16536 | 267.7 | 2117.9 | +2864.4 | 11% |
| sigma=0.03, can start again | 120 | 5000 | 5250 | 34541 | 537.8 | 2117.9 | +2594.3 | 20% |
| sigma=0.06, shut out for good | 0 | 100 | 105 | 0 | 0.4 | 535.3 | -430.7 | 0% |
| sigma=0.06, shut out for good | 10 | 163 | 171 | 284 | 4.9 | 784.9 | -618.8 | 1% |
| sigma=0.06, shut out for good | 20 | 265 | 279 | 671 | 11.1 | 1136.8 | -869.3 | 1% |
| sigma=0.06, shut out for good | 40 | 704 | 739 | 2147 | 35.0 | 2263.9 | -1559.6 | 2% |
| sigma=0.06, shut out for good | 60 | 1868 | 1961 | 5894 | 95.8 | 4010.3 | -2144.8 | 2% |
| sigma=0.06, shut out for good | 81 | 5000 | 5250 | 16536 | 267.7 | 5343.7 | -361.5 | 5% |
| sigma=0.06, shut out for good | 120 | 5000 | 5250 | 34541 | 537.8 | 5343.7 | -631.6 | 9% |
| sigma=0.06, can start again | 0 | 100 | 105 | 0 | 0.4 | 20.4 | +84.2 | 2% |
| sigma=0.06, can start again | 10 | 163 | 171 | 284 | 4.9 | 270.0 | -103.9 | 2% |
| sigma=0.06, can start again | 20 | 265 | 279 | 671 | 11.1 | 621.9 | -354.4 | 2% |
| sigma=0.06, can start again | 40 | 704 | 739 | 2147 | 35.0 | 1748.9 | -1044.7 | 2% |
| sigma=0.06, can start again | 60 | 1868 | 1961 | 5894 | 95.8 | 3495.4 | -1629.9 | 3% |
| sigma=0.06, can start again | 81 | 5000 | 5250 | 16536 | 267.7 | 4828.8 | +153.4 | 5% |
| sigma=0.06, can start again | 120 | 5000 | 5250 | 34541 | 537.8 | 4828.8 | -116.6 | 10% |
