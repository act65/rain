# Offline: an allowance backed by locked funds

Started 2026-11-20. Follows `offline_race/`. Serves the design of `OfflineAllowanceScript`.

## Question

Before losing the connection a payer locks funds on the chain and carries a certificate: "this payer may have
at most `A` outstanding in notes until `T`", signed by a key every shop knows. Every note quotes the
certificate. Notes up to `A` are paid from the locked funds. Any set of notes under one certificate that
totals more than `A` proves an overspend, to anyone, with no chain. On the chain the first note that takes the
total past `A` forfeits a further deposit (the float) to whoever presents it, and destroys a bonded amount of
reputation.

Copying a note is still possible, so this is still a race. What does the allowance change?

1. Does it change how much an overspender gets accepted?
2. What do shops lose, and what do payers who do not overspend cost them?
3. How large must the float be for overspending to lose money, and how does that depend on the attacker's
   speed?
4. Can a shop that lies shut an honest payer out?

Kind: deductive, with simulation as a check. The race arms have randomness (20 seeds).

## Decision it feeds

Whether to recommend the allowance script over plain notes, what float a shop should ask to see, and what the
posts may claim.

## Setup

As `offline_race/`: a market of 1,000 shops; the attacker visits one unvisited shop per unit of time (ten with
ten helpers) and asks each for the most it accepts. Each shop accepts a note of `A / m` (`m` = 5) unless the
notes it knows of under the certificate, with the new one, would exceed `A`. News travels through the chain:
an accepted note reaches it `d` = 5 later, and a shop syncs `rho` = 0.2 times per unit of time. Amounts are in
units of `A`.

| arm | |
|---|---|
| race | the attacker's notes accepted, with the certificate, against the same race without one (`offline_race/`, arm D: 2.91) |
| expiry | the certificate lasts `T` = 10 units of time; shops refuse it afterwards |
| loss | what shops lose in all, with locked funds of `A`, against plain notes from a payer who pays nothing |
| ordinary payers | 100,000 payers drawn from the belief of `offline/` (thresholds, 2% shocks), each spending their allowance at five shops: how many notes go unpaid, against the 10% of plain notes |
| float | the attacker's gain, `take - A - float`, at floats of 0, 1, 2 and 5 times `A`, alone and with ten helpers |
| liars | gossip (one swap per shop per unit of time): one shop spreads "this payer has overspent" about an honest payer. Shops either believe hearsay, or act only on notes they can check |

Controls. The loss arm without locked funds must reproduce `offline_race/` (2.91 limits lost). In the liars
arm, shops that believe hearsay must shut the honest payer out (if not, the lie is not implemented).

## Predictions (written 2026-11-20, before running)

1. **The race is unchanged.** A shop that has heard nothing accepts, with or without a certificate. The take
   is 2.90 limits (within 5%), as in `offline_race/`.
2. **Expiry caps the take at the shops reachable in the certificate's life**: `min(race, k T / m)`. With
   `T` = 10 that is 2 limits alone (the cap binds: 2.0, within 2%) and 20 with ten helpers.
3. **Shops lose one limit less, and ordinary payers cost them nothing.** With locked funds the shops' loss is
   the take less `A`: 1.90 in place of 2.90. A payer who stays within the allowance always pays, shock or no
   shock, so unpaid notes among ordinary payers fall from 10% to 0.
4. **The float that deters is the excess take, and it scales with the attacker's speed.** Alone, the attacker
   gains 1.90, 0.90, -0.10 and -3.10 times `A` at floats of 0, 1, 2 and 5. With ten helpers (take 20.9) the
   gain is positive at all four: 19.9, 18.9, 17.9, 14.9.
5. **Hearsay can be used to shut out an honest payer; proof cannot.** Shops that believe hearsay: more than
   95% of the market refuses the honest payer within `2 ln(M) / g` = 14 units of time. Shops that act only on
   notes they can check: none.

Failure would be: a take with the certificate above the take without it; ordinary payers leaving notes unpaid;
or an honest payer refused by a shop that checks.

## Scope

The attester's key is trusted to sign only certificates for allowances that exist on the chain (the oracle,
with the questions that raises, see TODO). Shops know the attester's key and the time. The bonded reputation
is not valued here (`fee_use/`: about 3% of what a borrower on a ladder owes). The allowance covers payments
only: a shop that wants to give credit beyond the locked funds is a lender again, and `offline/` applies.

## Outcome (2026-11-20)

Numbers are in `results/SUMMARY.md`. Both controls behaved: without locked funds shops lose the whole take
(2.94 allowances, fees included), and shops that believe hearsay shut the honest payer out.

| prediction | outcome |
|---|---|
| 1. the race is unchanged: 2.90 | Held: 2.91 with a certificate and without, identical run by run. This is by construction (a shop that has heard nothing accepts either way), and the run confirms the two rules were implemented as the same rule. |
| 2. expiry caps the take at `min(race, k T / m)`: 2 alone, 20 with ten helpers | Held alone (2.00 in every run). **Wrong with helpers: 17.1, not 20.** The two limits act together, not one or the other: within the certificate's life the news has already caught up with some of the shops the helpers reach. |
| 3. shops lose one limit less (1.90 against 2.90); ordinary payers leave nothing unpaid | Held: 1.94 against 2.94, the difference from my figures being the 1% fee, which I left out. Payers who stay within the allowance leave 0 of 10,000 notes unpaid. With plain notes the same payers leave 2.6% unpaid (the 2% hit by a shock, on a sample of 2,000). The 10% I quoted is the rate in `offline/`, where the limit is credit; this arm compares like with like. |
| 4. the attacker's gain alone: 1.90, 0.90, -0.10, -3.10 at floats of 0, 1, 2, 5; positive at all four with ten helpers | Held: 1.91, 0.91, -0.09, -3.09; and 20.1, 19.1, 18.1, 15.1. |
| 5. hearsay shuts out more than 95% of the market by time 14; proof shuts out nobody | Held: 95.5%, and none. |

What this shows:

- **The allowance does not win the race.** Copies still reach shops that have not heard. What an attacker
  gets accepted is the same with or without it.
- **It separates payment from credit.** A payer who stays within the allowance is certain to pay, whatever
  happens to them, so a shop accepting such a note needs no belief about the payer at all. The only risk left
  is deliberate overspending.
- **It takes one allowance off the shops' loss**, because the locked funds pay the first notes presented.
- **The float is a deterrent, and its size is a statement about speed.** Overspending loses money when the
  float exceeds what the attacker can get accepted beyond the allowance: about two allowances here for an
  attacker alone, and more than fifteen for one with ten helpers. A shop can read the float off the
  certificate (once it is added to it) and accept accordingly.
- **Proof cannot be used against an honest payer.** A shop that acts only on notes it can check cannot be
  told to refuse someone: the notes that would prove an overspend do not exist.
- **Expiry and news act together.** A short-lived certificate caps the take at the shops reachable in its
  life, and within that life the news is already working.

What it does not show: what a carrier's reward does to the delay; what the bonded reputation adds; whether
payers would lock two or three times what they mean to spend. When this was run the certificate did not state the float, so a shop could not see it
offline. It now does (`rain.offline.Certificate.float`).
