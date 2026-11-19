# Graduation: results

Commit `247495c` (dirty: False), 2026-11-19T16:05:58+00:00.

A stranger's default is worth 94.24.
One guaranteed loan of 10,000, outstanding a cycle and repaid, costs the ring 128.6 (fees sunk: 125.0).

## The rule: best gain over a stranger's default, by strategy (defaulting on any loan from the 1st to the 61st)

| record made by | amount | best gain |
|---|---|---|
| none | 0 | +0.00 |
| guaranteed, once | 1,000 | -7.33 |
| guaranteed, once | 10,000 | -72.56 |
| guaranteed, every cycle | 1,000 | -12.86 |
| guaranteed, every cycle | 10,000 | -128.57 |
| wash, once | 1,000 | -0.36 |
| wash, once | 10,000 | -3.60 |
| wash, once | 100,000 | -36.01 |
| wash, every cycle | 1,000 | -0.36 |
| wash, every cycle | 10,000 | -3.60 |
| wash, every cycle | 100,000 | -36.01 |

671 strategies searched. Best: none (gain +0.00). Worst: wash, every cycle of 100,000, defaulting on loan 61 (-10,833).

## Controls: the ring's best gain under weaker rules

| rule | best strategy | gain | best gain defaulting on loan 1, 2, 3, 6, 21, 41 |
|---|---|---|---|
| evidence alone | wash, once of 100,000, default on loan 1 | +93,519 | +93,519, +88,388, +83,502, +70,196, +26,386, +1,085 |
| no growth limit | wash, once of 100,000, default on loan 2 | +89,027 | +0, +89,027, +84,141, +70,835, +27,024, +1,723 |
| cost counted every time | wash, every cycle of 100,000, default on loan 21 | +23,493 | +0, +524, +1,528, +7,305, +23,493, +9,569 |

## An honest newcomer who needs 10,000 a cycle

With a guarantor: unsecured offer 100, 168, 239, 313, 392, 474, ... ; the guaranteed part reaches zero in cycle 44 (recurrence: 43). Expected cost to the guarantor over that time: 3,176.
Alone: unsecured offer 100, 100, 100, 100, 100, 100, ...

| cycle | unsecured | guaranteed |
|---|---|---|
| 0 | 100 | 10,000 |
| 1 | 168 | 9,832 |
| 5 | 474 | 9,526 |
| 10 | 950 | 9,050 |
| 20 | 2,334 | 7,666 |
| 30 | 4,587 | 5,413 |
| 40 | 8,258 | 1,742 |
| 45 | 10,000 | 0 |
| 50 | 10,000 | 0 |

## Credit per reputation point

2,500 points earned by washing: offered 162.50, i.e. 0.0250 per point (predicted 0.0250).
