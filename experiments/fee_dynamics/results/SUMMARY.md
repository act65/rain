# Fee dynamics: results

Commit `1805efb` (dirty: True), 2026-11-19T12:36:09+00:00.

| arm | c | fee exponent (fitted / predicted) | max value/fee | min value/fee | cycles where farming pays |
|---|---|---|---|---|---|
| A1_baseline | 0.12 | -0.888 / -0.880 | 0.631 | 0.313 | 0 [] |
| A2_runaway | 1.50 | 0.497 / 0.500 | 2.918 | 0.743 | 170 [5, 6, 7, 8, 9, 10] |
| A3_control_no_margin | 0.00 | n/a | inf | inf | 295 [5, 6, 7, 8, 9, 10] |
| A4_shock | 0.12 | -0.057 / -0.880 | 5.224 | 0.423 | 31 [21, 22, 23, 24, 25, 26] |
| A5_shock_farmers | 0.12 | 0.018 / -0.880 | 4.095 | 0.397 | 28 [24, 25, 26, 27, 28, 29] |

## Value of a promise / fee paid, by cycle

| arm | t=5 | t=20 | t=49 | t=50 | t=51 | t=52 | t=53 | t=100 |
|---|---|---|---|---|---|---|---|---|
| A1_baseline | 0.313 | 0.436 | 0.523 | 0.524 | 0.526 | 0.528 | 0.529 | 0.578 |
| A2_runaway | 2.918 | 1.996 | 1.472 | 1.462 | 1.453 | 1.443 | 1.434 | 1.169 |
| A3_control_no_margin | inf | inf | inf | inf | inf | inf | inf | inf |
| A4_shock | 0.423 | 0.971 | 4.925 | 5.224 | 1.310 | 0.752 | 0.529 | 0.578 |
| A5_shock_farmers | 0.397 | 0.842 | 3.868 | 4.095 | 1.205 | 0.794 | 0.557 | 0.590 |

## Fee (DMD per promise) and value of a point over time

| arm | fee t=1 | t=5 | t=20 | t=50 | t=100 | last | point value t=5 | t=100 | last |
|---|---|---|---|---|---|---|---|---|---|
| A1_baseline | 0.0024 | 0.001415 | 0.0006044 | 0.0002972 | 0.0001672 | 6.531e-05 | 1.774e-05 | 3.866e-06 | 1.647e-06 |
| A2_runaway | 0.03 | 0.03119 | 0.04752 | 0.06954 | 0.09556 | 0.2939 | 0.003641 | 0.004467 | 0.008735 |
| A3_control_no_margin | 0 | 0 | 0 | 0 | 0 | 0 | 1.505e-05 | 2.616e-06 | 9.912e-07 |
| A4_shock | 0.0024 | 0.001415 | 0.0006044 | 0.0002972 | 0.001665 | 0.0006505 | 2.395e-05 | 3.851e-05 | 1.641e-05 |
| A5_shock_farmers | 0.0024 | 0.001415 | 0.0006044 | 0.0002972 | 0.001389 | 0.0005984 | 2.246e-05 | 3.274e-05 | 1.514e-05 |

## A5: the farmer after the shock

- wash promises by cycle: {'50': 1000, '51': 1000}
- fees paid 1.2 DMD, dividends collected (discounted to the shock) 2.4 DMD, profit 1.1 DMD
- farmer's final share of all reputation: 0.028
- change in honest holders' discounted dividends caused by the farming: -2.3 DMD (from 11.1)
