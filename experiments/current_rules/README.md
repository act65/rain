# The first four experiments, under the current rules

Started 2026-11-19. `default_frontier/`, `fee_dynamics/`, `exit_scam/` and `sybil/` studied the original
rules, and their findings are why the rules changed. This experiment asks the same four questions of the
rules the contracts now implement: a fee proportional to the promise (1%, minimum 0.1), a fixed price per
point (`kappa` = 0.04), decay (`delta` = 0.03 per cycle), fees paid out, and no starting reputation.
Discount rate `r` = 0.05 throughout.

The way fees are paid out changed after this experiment was first run, as a result of its part B. The
predictions and first outcome below are for the design at the time (fees paid out in full each cycle, with a
genesis allocation and a reserve fund). The last section gives the re-run under the present design (all fees
through a payout fund released at the decay rate). `results/SUMMARY.md` is from the re-run.

In steady state a point earns `kappa * delta` per cycle and is worth `v = kappa * delta / (r + delta)` = 0.015 DMD.
It costs `kappa` = 0.04 DMD in fees. Their ratio, `(r + delta) / delta` = 2.67, plays the part that the
keeper's margin (1.5) played before.

Code: `rain.economics.current_*`, `Economy.current_rules`. Kind: deductive for A, C and D (formulas checked by
simulation); B is a simulation of dynamics.

## A. How large a loan can a given reputation safely back?

A defaulter keeps the amount due. They lose the bond and the flat penalty (worth `v` per point), the reward
for repaying (worth `delta / (r + delta)` of the fee), and access to future loans, each of which would
yield a surplus `sigma * P`, cost its fee and return reputation worth 37.5% of that fee.

Predictions (written before running):

1. Simulated largest safe loan agrees with `current_max_safe_loan` within 0.5% on every grid point.
2. With no surplus and everything bonded, a point backs about `v` = 0.015 DMD of credit. To be trusted with
   `P` on the strength of a bond alone costs about `2.67 P` in fees, which is `267 P` of repaid loans at a 1% fee.
   (Under the original rules it was `1.5 P`.) Reputation valued by its dividends is still worth less as
   collateral than the money spent acquiring it.
3. Access to future credit starts to count once the surplus per loan exceeds the net cost of its fee:
   `sigma > phi (1 + i) r / (r + delta)` = 0.66% of the principal. Below that, surplus changes nothing.
4. The demo's second loan (110 DMD at 5 DMD interest, 20 points bonded out of 26.25) is about 140 times
   larger than the bond alone makes safe.
5. Control: with a point price of zero (worthless reputation) and no surplus, default pays at every size.

## B. Does farming pay, and is the value of a point stable?

`anchored_fee/` showed value / cost settles at `delta / (r + delta)` = 0.375 under steady activity and
survives a one-off grant. Not tested there: a lasting change in activity. The genesis allocation is sized
for 100 DMD of fees per cycle.

Arms, each starting from the steady state at cycle 300: activity doubles; multiplies by 10; divides by 10;
multiplies by 10 with a farmer (up to 1000 wash promises per cycle whenever a point's expected value exceeds its cost).

Predictions:

6. Doubling: value / cost peaks below 1 (about 0.6). No farming.
7. Tenfold rise: value / cost peaks between 1.4 and 1.8. For a while supply is a tenth of what the new fee
   flow will support, so each point collects ten times the usual dividend. **Farming pays after a large,
   lasting surge in activity.**
8. Tenfold fall: value / cost falls to between 0.05 and 0.2 and recovers as supply decays. No exploit; reputation
   earned during the slump is poor value.
9. With the farmer: the farmer profits, and by adding supply pulls value / cost back towards 1 faster.
   Honest holders' dividends are lower than without the farmer.

## C. Exit scam

Lenders advance `ell` per bonded point. The attacker holds 100 points and may buy more at `kappa` each.

10. Simulated profit equals `(ell - v) * existing + (ell - kappa) * bought` within 1%.
11. Thresholds: turning existing reputation pays when `ell > v`; buying reputation to burn pays when
    `ell > kappa`, i.e. 2.67 `v` (it was 1.5 `v`).
12. The demo's ratio (110 DMD against 20 points, 5.5 DMD per point) is about 367 times `v`.

## D. Disposable identities

13. An identity with no reputation extracts nothing from a lender who lends against bonds: there is nothing
    to bond. (Under the original rules a free 100-point identity extracted about 2000 DMD from a naive lender.)
14. Bought reputation: profit per 100 points is `100 (ell - kappa)` minus the fee on the loan; negative
    against a careful lender (`ell = 0.9 v`), positive against one lending 5.5 per point.
15. Vouched (a sponsor bonds 100 of its own points): `100 (ell - v)` minus the fee.
16. Scaling: `N` bought identities attacking in one cycle. Profit per identity does not depend on `N`
    against a lender with a fixed ratio. The sybils' fees are paid out as dividends after their reputation is
    destroyed, so honest holders gain and the lenders bear the loss.

Failure would be: a formula disagreeing with its simulation; farming paying under steady activity; or an
identity with no reputation extracting anything.

## Scope

As the experiments this follows: constant parameters, passive lenders, no response of honest users to
prices. Part B's shocks are permanent step changes; gradual growth is not tested.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. A: simulation matches formula within 0.5% | Held: worst relative error 1.1e-04 over 16 grid points. |
| 2. a fully bonded point backs about `v`; 2.67 units of fees per unit of credit | Held: 0.957 `v` per point; 2.67 (267 units of repaid loans). |
| 3. surplus counts only above 0.66% of the principal | Held: a 0.5% surplus changes nothing at any grid point; 2% and 4.5% raise the safe loan. For small loans the minimum fee raises the threshold further (R = 500 with a 100-point bond is unaffected even at 2%). |
| 4. demo's second loan about 140 times too large | **Wrong number: 267 times** (largest safe loan 0.41 DMD). I used the fee on the 110 DMD loan when working out the forgone reward; at the safe size the loan pays only the minimum fee. |
| 5. control | Held. |
| 6. B: doubling peaks at about 0.6 | Held: 0.596. No cycle above 1. |
| 7. tenfold rise peaks between 1.4 and 1.8 | Just below the range: 1.365, above 1 for 4 cycles. The conclusion stands: farming pays after a large, lasting surge. |
| 8. tenfold fall: 0.05 to 0.2 | Held: 0.056 at the shock, back to 0.29 after 100 cycles. |
| 9. farmer profits, pulls value / cost towards 1, honest holders lose | Partly. The farmer makes 5000 wash promises in the first 5 cycles for a profit of 649 DMD on 4546 DMD of fees, and honest holders' discounted dividends fall 4.3%. **But value / cost at the shock is higher with the farmer (1.53 against 1.37)**: the farmer's own fees are paid out as dividends that cycle. It is above 1 for 3 cycles instead of 4. |
| 10. C: simulation matches formula | Held: worst disagreement 9.5e-08. |
| 11. thresholds at `v` and `kappa` = 2.67 `v` | Held: buying more reputation lowers the profit below 2.67, changes nothing at 2.67, raises it above. |
| 12. demo ratio 367 times `v` | Held. |
| 13. D: an identity with no reputation extracts nothing | Held: it loses the minimum fee (0.1 DMD). |
| 14, 15. bought and vouched identities | Held: -2.75 and -0.25 against the careful lender; +540.5 and +543 at the demo's ratio. |
| 16. scaling | Held: 545 DMD per identity at every `N`; honest holders' next dividend per point rises 5% (`N` = 1) to 50-fold (`N` = 1000). |

What changed from the original rules, and what did not:

- **Fixed: the collapse.** A point has a stable value (0.015 DMD) set by three parameters, with no keeper.
- **Fixed: free reputation.** A new identity can extract nothing; under the original rules it extracted
  about 2000 DMD from a naive lender and 16 DMD from a careful one.
- **Fixed: farming in the steady state**, at any parameters, and after a one-off grant (`anchored_fee/`).
- **Not fixed, and slightly worse: reputation as collateral.** A bonded point still backs only its dividend
  value, and that is now 37.5% of what the point cost instead of 67%. Being trusted with `P` on a bond alone
  costs `2.67 P` in fees. This is the price of the anti-farming guarantee: the two are the same ratio.
- **Not fixed: lenders who lend against the score.** At the demo's 5.5 DMD per bonded point, a scam returns
  545 DMD per bought identity and scales without limit. The protocol cannot stop a script lending too much;
  it can only make the record honest. What deters default at useful loan sizes is losing access to future
  credit (prediction 3), which depends on the lender's rule, not on the points.
- **New exposure: a surge in activity.** Supply takes about `1 / delta` cycles to catch up with a higher fee
  flow, and until it does each point is over-rewarded. A tenfold rise makes farming pay for about four
  cycles. Doubling does not. The farmer's gain is modest (14% on fees) and costs holders 4%.

Not tested: gradual growth in activity (which never opens as wide a gap), and a point price that adjusts.

## Re-run after the payout fund was adopted (2026-11-19)

`surge_fixes/` tested three remedies for the surge exposure found in part B, and the contracts adopted the one
that worked: every fee goes into a payout fund, which shares out a fraction of itself equal to the decay rate
each cycle. `Economy.current_rules` now models that. `surge_fixes/` predicted value / cost would hold at 0.375
through a surge.

| part | result under the present design |
|---|---|
| A | Unchanged (it is a steady-state result): worst error 1.1e-04; 2.67 units of fees per unit of credit; the demo's second loan 267 times too large for its bond. |
| B | **The exposure is gone.** Value / cost is 0.375 before, at and after a doubling, a tenfold rise and a tenfold fall. The farmer makes no wash promises. |
| C | Unchanged: worst disagreement 9.5e-08; thresholds at `v` and `kappa`. |
| D | Per-identity profits unchanged. In the scaling arm the sybils' fees now reach honest holders gradually: their next dividend per point rises 0.2% (`N` = 1) to 150% (`N` = 1000), instead of 5% to 50-fold. |

So of the list under "What changed from the original rules", the "new exposure" no longer applies. The two
items marked "not fixed" stand: they are about what a bond can secure and what lenders choose to do, and
`standing_value/` gives the fuller account of the first.
