# What should the fees pay for? Results

Commit `c96370a` (dirty: False), 2026-11-20T06:25:34+00:00.

| rule | net cost of washing one unit | net cost of an honest promise of one unit | safe trust in unknown counterparties |
|---|---|---|---|
| 1. dividend (current) | 0.6250% | 0.6250% | 3.32% |
| 2. burn | 1.0000% | 1.0000% | 5.25% |
| 3. counterparty | 0.0000% | 1.0000% | 0.00% |
| 4. insurance | 1.0000% | 1.0000% | 5.25% |
| 5. work, presented by the payer | 0.3125% | 0.3125% | 1.67% |
| 5. work, presented by someone else | 0.8125% | 0.8125% | 4.29% |
| 6. per identity | 0.9998% | 0.9999% | 5.25% |
| 7. forfeitable dividend | 0.6250% | 0.6250% | 3.32% |

Control: under the current rules a wash costs 0.6250% in the model of the contracts.

## Rule 4: insurance, with a ring that fakes defaults

| fake defaults, as a multiple of honest ones | share of each claim paid | ring's fee | ring receives | ring's share of the pool | honest promisees recover, of their loss |
|---|---|---|---|---|---|
| 0 | 100.0% | 0 | 0 | 0.0% | 50.0% |
| 1 | 51.0% | 200 | 5,100 | 50.0% | 25.5% |
| 10 | 10.9% | 2,000 | 10,909 | 90.9% | 5.5% |
| 100 | 3.0% | 20,000 | 29,703 | 99.0% | 1.5% |

The ring profits while claims are paid at more than 2% of the cover promised.

## Rule 6: per identity

| ring's identities per honest identity | ring's share of all revenue |
|---|---|
| 0.1 | 9.1% |
| 1.0 | 50.0% |
| 10.0 | 90.9% |

## Rule 7: what a defaulter on a ladder would forfeit

Reputation worth 3.06% of the amount due (model), 3.06% (formula). The prediction in the README counted the fee on the loan being defaulted on: 3.43%.
