# Dividend concentration: results

Commit `514658d` (dirty: False), 2026-11-19T13:27:43+00:00. 200 agents, 800 cycles, 5 seeds; mean (min to max over seeds).

| measure | decay 0.03 | decay 0.005 | decay 0.0 |
|---|---|---|---|
| late arrivals' standing relative to early, cycle 400 | 0.982 (0.970 to 0.992) | 0.598 (0.586 to 0.613) | 0.369 (0.359 to 0.384) |
| late arrivals' standing relative to early, cycle 800 | 0.998 (0.985 to 1.008) | 0.950 (0.938 to 0.960) | 0.684 (0.672 to 0.691) |
| unreliable agents' standing relative to reliable early agents, cycle 800 | 0.236 (0.210 to 0.252) | 0.084 (0.081 to 0.089) | 0.027 (0.026 to 0.029) |
| Gini of reputation, reliable agents | 0.492 (0.452 to 0.540) | 0.492 (0.453 to 0.539) | 0.499 (0.461 to 0.540) |
| Gini of activity, reliable agents | 0.492 (0.452 to 0.541) | 0.492 (0.452 to 0.541) | 0.492 (0.452 to 0.541) |
| reliable agents: dividends / fees, last 200 cycles | 1.095 (1.078 to 1.107) | 1.094 (1.060 to 1.113) | 1.179 (1.140 to 1.208) |
| unreliable agents: dividends / fees, last 200 cycles | 0.517 (0.487 to 0.544) | 0.198 (0.187 to 0.213) | 0.086 (0.079 to 0.095) |
| top tenth by activity: share of dividends, last 100 cycles | 0.360 (0.300 to 0.411) | 0.355 (0.288 to 0.406) | 0.353 (0.293 to 0.417) |
| top tenth by activity: share of reputation | 0.360 (0.299 to 0.400) | 0.354 (0.288 to 0.407) | 0.353 (0.292 to 0.417) |
| top tenth by activity: share of activity | 0.370 (0.326 to 0.416) | 0.370 (0.326 to 0.416) | 0.370 (0.326 to 0.416) |
