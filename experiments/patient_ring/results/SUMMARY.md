# A patient ring: results

Commit `723a2bd` (dirty: False), 2026-11-19T16:30:20+00:00.

The ring's best gain over a stranger's default, by its own discount rate (rows) and the sunk share the lender uses (columns).
154 strategies per column.

| ring discounts at | lender assumes at least 5% (share 0.625) | lender assumes at least 2% (share 0.400) | lender assumes at least 0% (share 0.000) |
|---|---|---|---|
| 5% | +0.0 | +0.0 | +0.0 |
| 4% | +243.6 (wash, every cycle of 100,000, default on loan 31; 0.8% of fees) | +0.0 | +0.0 |
| 3% | +1,946.5 (wash, every cycle of 100,000, default on loan 31; 6.3% of fees) | +0.0 | +0.0 |
| 2% | +4,915.8 (wash, every cycle of 100,000, default on loan 31; 15.9% of fees) | +0.0 | +0.0 |
| 1% | +10,352.9 (wash, every cycle of 100,000, default on loan 31; 33.4% of fees) | +5,307.5 (wash, every cycle of 100,000, default on loan 46; 11.5% of fees) | +0.0 |
| 0% | +21,184.8 (wash, every cycle of 100,000, default on loan 31; 68.3% of fees) | +20,875.7 (wash, every cycle of 100,000, default on loan 46; 45.4% of fees) | +0.0 |

Cycle in which an honest newcomer needs no guarantor: share 0.625: 44, share 0.400: 51, share 0.000: 95.
