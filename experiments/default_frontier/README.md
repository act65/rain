# Default-rationality frontier

> **This experiment studies the original rules** (flat reward, fee keeper, yield-only treasury, no decay), which the
> contracts no longer use. Its findings are part of why they changed. For the same question under the current
> rules see `../current_rules/`.

Started 2026-11-19. Serves the blog's claim that "the value of a good standing always exceeds the
one-time payoff of betraying it".

## Question

For a borrower with reputation `R` who bonded `s` of it against a loan of `P` at interest `i`: is
repaying better than defaulting? Equivalently, what is the largest safe loan `P*`?

Kind: deductive. It follows from the protocol rules, so the answer is a formula
(`rain.economics.max_safe_loan`); the simulation is an independent check of the formula.

## Decision it feeds

How much a lender should advance per point of reputation, and therefore whether reputation valued
by dividends alone can support undercollateralised lending at a useful scale.

## What is compared

A defaulter keeps `P(1+i)`. They lose the bond, the flat penalty (at most what is left), the reward
for repaying, and access to future loans. They keep collecting dividends on whatever reputation remains.
The honest alternative is the better of "repay and keep borrowing `P` every cycle" (surplus `sigma * P`
per loan, minus the fee, plus the reputation earned) and "repay and stop".

`run.py`:
- **A. Formula against simulation.** For a grid of `(R, s, v, sigma)`, find the `P` at which the discounted
  payoffs of the strategies cross, by simulating each strategy in `Economy` for 400 cycles and bisecting.
- **B. The frontier.** `P*` per point of reputation, in units of `v`.
- **C. The demo loan**, and the total credit the whole system can safely back.
- **Control that must fail.** With worthless reputation (`v = 0`) and no surplus, no loan is safe.

## Predictions (written 2026-11-19, before running)

1. Simulated `P*` agrees with the formula within 0.5% on every grid point.
2. With no surplus from borrowing, `P* = v * (s + min(100, R - s) + 25) / (1 + i)`: a point of bonded
   reputation backs about `v` of credit, no more.
3. The demo loan is far too large: `P*` for the demo borrower (R = 100, s = 50, v = 0.3077) is about
   36.6 DMD against a 1000 DMD loan, a factor of about 27.
4. System-wide, all reputation together safely backs credit of at most `D / r` (the present value of all
   dividends) when there is no surplus. With dividends equal to the yield `y` on the treasury that is
   `(y / r) * treasury`: 8% of the treasury at `y = 0.004`, `r = 0.05`.
5. Control: with `v = 0` and `sigma = 0` the simulated gain from defaulting is positive for every `P > 0`.

Failure would be: the simulation disagrees with the formula (then one of them mis-states the protocol),
or the control shows a safe loan.

## Scope

A positive result says the formula describes the model, and the model matches the contracts. It does not
say real borrowers have these payoffs: `sigma` and `r` are inputs, not measurements, and a borrower who
can create a new identity loses nothing by being excluded (see `sybil/`).

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. simulation matches formula within 0.5% | Held: worst relative error 9.5e-05 over 36 grid points. |
| 2. with no surplus a bonded point backs about `v` | Held: `P* / (v R)` is 0.95 to 0.98 with everything bonded (R of 1000 and 10,000). |
| 3. demo loan about 27 times too large | Held: `P*` = 36.63 DMD against 1000 DMD (27.3 times). Defaulting on the demo loan gains 1011.54 DMD. |
| 4. all reputation backs credit of 8% of the treasury | Held (it is `y / r` by construction). |
| 5. control | Held: defaulting gains exactly the amount owed at every loan size. |

What the frontier table adds:

- **Reputation valued by dividends works like collateral worth `v` per point.** It does not create credit beyond
  its own cash value.
- **A small surplus from borrowing changes nothing.** For small reputations (R = 100) the safe loan is the same
  at every surplus rate tested, because the fee per loan exceeds the surplus on a loan that small: continued
  access is not worth protecting. Earning reputation is itself a net cost (the fee is `m` times the value of
  the reputation it buys), so "I want to keep earning reputation" is never a reason to repay.
- **Access to future credit is what scales.** At `sigma / r = 1` the safe loan is 15 to 20 times `v R`; above
  `1 + i` large loans are safe whatever the reputation. This deterrent does not depend on the reputation
  score at all, only on exclusion being permanent, which is the question `sybil/` takes up.
- **Delinquent users keep collecting dividends** on their remaining reputation. The model and contracts agree
  on this; it weakens the penalty and looks unintended.
