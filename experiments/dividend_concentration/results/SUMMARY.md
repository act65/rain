# Dividend concentration: results

Commit `8770db0` (dirty: False), 2026-11-19T14:49:02+00:00. 200 agents, 800 cycles, 5 seeds; mean (min to max over seeds).

| measure | decay 0.03 | decay 0.005 | decay 0.0 |
|---|---|---|---|
| late arrivals' standing relative to early, cycle 400 | 0.982 (0.970 to 0.992) | 0.598 (0.586 to 0.613) | 0.369 (0.359 to 0.384) |
| late arrivals' standing relative to early, cycle 800 | 0.998 (0.985 to 1.008) | 0.950 (0.938 to 0.960) | 0.684 (0.672 to 0.691) |
| unreliable agents' standing relative to reliable early agents, cycle 800 | 0.414 (0.389 to 0.436) | 0.158 (0.152 to 0.166) | 0.052 (0.050 to 0.054) |
| Gini of reputation, reliable agents | 0.492 (0.452 to 0.540) | 0.492 (0.453 to 0.539) | 0.499 (0.461 to 0.540) |
| Gini of activity, reliable agents | 0.492 (0.452 to 0.541) | 0.492 (0.452 to 0.541) | 0.492 (0.452 to 0.541) |
| reliable agents: dividends / fees, last 200 cycles | 1.070 (1.055 to 1.081) | 1.083 (1.050 to 1.101) | 1.174 (1.135 to 1.203) |
| unreliable agents: dividends / fees, last 200 cycles | 0.645 (0.631 to 0.659) | 0.256 (0.245 to 0.266) | 0.112 (0.106 to 0.120) |
| top tenth by activity: share of dividends, last 100 cycles | 0.356 (0.299 to 0.406) | 0.353 (0.288 to 0.403) | 0.352 (0.293 to 0.415) |
| top tenth by activity: share of reputation | 0.356 (0.298 to 0.395) | 0.352 (0.287 to 0.403) | 0.352 (0.292 to 0.415) |
| top tenth by activity: share of activity | 0.370 (0.326 to 0.416) | 0.370 (0.326 to 0.416) | 0.370 (0.326 to 0.416) |
