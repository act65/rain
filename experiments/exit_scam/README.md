# Exit scam

> **This experiment studies the original rules** (flat reward, fee keeper, yield-only treasury, no decay), which the
> contracts no longer use. Its findings are part of why they changed. For the same question under the current
> rules see `../current_rules/`.

Started 2026-11-19. Serves the blog's "Forfeiture-of-Present-Value" and "Gain-of-Future-Value" mechanisms:
does accumulated reputation deter someone who plans to leave?

## Question

An agent bonds all of their reputation against as many loans as lenders will give, and defaults on every
one. Lenders advance `ell` currency units per bonded point. Before leaving, the agent may buy more
reputation by keeping `n` cheap promises (each costs the fee `m * v * g` and earns `g` points).

When is this profitable, and what must lenders do to make it unprofitable?

Kind: deductive (`rain.economics.exit_scam_profit`). The simulation checks the accounting through the
model's actual mechanics: concurrent bonds, fees, defaults.

## Decision it feeds

The lending ratio a lender can safely offer, and what it costs an honest user to reach a given credit line.

## Setup

`Economy` with a large passive bloc, a treasury sized so that a point is worth `v`, the fee at the keeper's
level, an attacker with 100 points and deep-pocketed lenders. The attacker keeps `n` one-unit loans, then
splits all reputation into four bonds, borrows `ell` per bonded point from four lenders, and defaults.
Profit is the change in the attacker's money minus `v * 100`, the dividends the original reputation would
have earned if kept.

## Predictions (written 2026-11-19, before running)

1. Simulated profit equals `(ell - v) * R0 + n * g * (ell - m * v)` within 1% (or 0.01 DMD) at every grid point.
2. So there are two thresholds. Turning existing reputation pays when `ell > v`. Buying reputation in order
   to burn it pays when `ell > m * v`: below that, more building lowers the profit; above it, raises it.
3. At the demo's lending ratio (1000 DMD against a 50-point bond, `ell = 20`, with `v = 0.3077`, so
   `ell / v = 65`) a 100-point identity extracts about 1969 DMD, and each additional kept promise adds
   about 488 DMD of profit.
4. A lender who keeps `ell <= v` is safe, and then an honest user who wants a credit line of `P` needs
   `P / v` points, which costs `m * P` in fees: 1500 DMD of fees to be trusted with 1000 DMD.

Failure would be: the simulation disagrees with the formula, or a profitable scam exists at `ell < v`.

## Scope

No time: building reputation is instantaneous and undiscounted, which favours the attacker slightly.
Exclusion costs the attacker nothing here (they are leaving); `default_frontier/` covers the borrower who
wants to stay. Lenders are passive.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. simulation matches formula | Held: worst disagreement 9.3e-08 over 42 grid points, once the fees on the four defaulted loans (which the formula leaves out) are added back. |
| 2. thresholds at `ell = v` and `ell = m v` | Held: profit is zero at `ell / v = 1` with no building; more building lowers profit below 1.5, has no effect at 1.5 and raises it above. |
| 3. demo ratio: 1969 DMD per 100-point identity, 488 DMD per extra promise | Held. |
| 4. a 1000 DMD credit line costs 1500 DMD in fees | Held: 3250 points, 130 kept promises. |

What this shows:

- **Above `ell = m v` the scam has no upper limit**: every promise kept beforehand adds to the take, so building
  a long honest history is the attack, not a defence against it. At the demo's ratio 40 kept promises turn a
  1969 DMD scam into a 21,500 DMD one.
- **Bonds do cap the exposure**, as intended: nothing can be borrowed against reputation that is already bonded.
  But the cap is in points, and lenders choose how much to lend per point.
- **The safe ratio makes reputation pointless as a route to credit.** A lender who stays at `ell <= v` cannot be
  scammed, and then being trusted with `P` requires first paying `m P` in fees. A user would do better to
  post `P` as ordinary collateral.
- Small scams are deterred by the fee on each loan (46 DMD across the four here), which the formula omits.
