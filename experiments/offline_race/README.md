# Offline: racing the news

Started 2026-11-20. Follows `offline/`, which bounded a double spender's take only for shops that guessed
correctly how many places the payer could reach.

## Question

A payer's signed note can be copied to as many shops as will take it. In `offline/` each shop accepts the
payer's limit `L` divided by a guess `m`, so an attacker who reaches `n` shops takes `n L / m`: without limit
in `n`. Nothing on the payer's side can bound this without shared state or trusted hardware. So the bound has
to come from the shops, and the question is what they must share, and how fast.

1. What does an attacker who can choose how many shops to visit take, under each rule a market could adopt?
2. If news of the payer's notes travels (between shops, or to the chain and back), how much does the attacker
   take before it overtakes them? Does that depend on the size of the market?
3. What does a rule that refuses payers when the shop's own information is old cost in availability?

Kind: deductive, with a simulation as a check. Arms C and D have randomness (20 seeds each).

## Decision it feeds

Which rule the reference payee should use, whether a reward for carrying notes to the chain is worth building,
and what the posts may claim about a double spend being bounded.

## Setup

A market of `M` shops. The attacker has a limit `L` and visits one shop they have not visited per unit of
time, signing a note for the most that shop accepts, and pays none of them. All speeds below are relative to
the attacker's: an attacker with `k` helpers carrying the same key visits `k` shops per unit of time.
`m` = 5 is the shops' guess of how many places a payer could be. The take is counted in limits (`L`).

| arm | rule |
|---|---|
| A (control) | each shop accepts `L / m` and learns nothing from anyone |
| B | each shop accepts `L / M` |
| C, gossip | each shop accepts `L / m`, unless the notes of this payer it knows of already total `L`. Shops holding notes pass everything they know to a random shop, and receive what it knows, `g` times per unit of time each |
| D, the chain | each shop accepts `L / m`, unless at its last sync the chain showed notes of this payer totalling `L`. Every accepted note reaches the chain `d` after it is signed (carriers). Each shop syncs at random, `rho` times per unit of time |
| D', freshness | as D, and a shop refuses everyone if its last sync is older than `T` |
| E, helpers | as D, with `k` = 10 helpers |

`M` = 100, 1,000 and (arm C) 10,000. `g` = 0.1, 0.3, 1, 3. `(d, rho)` = (1, 1), (5, 0.2), (20, 0.05).
`T` = 2 with (5, 0.2).

Control. Arm A must show the take growing in proportion to `M` (if it does not, copying a note to every shop
is not implemented).

## Predictions (written 2026-11-20, before running)

1. **Control: the take is `M / m` limits**: 20 at `M` = 100 and 200 at `M` = 1,000.
2. **Dividing by the market: exactly one limit**, and each shop accepts 1% of the limit at `M` = 100 and 0.1%
   at 1,000.
3. **Gossip: the take grows with the logarithm of the market.** News of each note spreads from shop to
   shop exponentially, so the attacker gets about `m + ln(M) / g` notes accepted, give or take a factor of
   two in the second term. At `g` = 1 the take is between 1.5 and 4 limits at `M` = 1,000, and going from
   `M` = 100 to 10,000 adds less than 2 limits. At `g` = 0.1 it is more than 5 limits at `M` = 1,000.
4. **The chain: the take does not depend on the size of the market.** It is
   `1 + (d + 1 / (exp(rho) - 1)) / m` limits: 1.32, 2.90 and 8.90 for the three settings, within 5%, and the
   same at `M` = 100 and 1,000 (while the market is large enough not to run out).
5. **Freshness is a hard cap, paid for in availability.** With `T` = 2, `d` = 5, `rho` = 0.2 no attacker takes
   more than `1 + (d + T) / m` = 2.4 limits in any run, and an honest payer finds a shop willing to deal
   `1 - exp(-rho T)` = 33% of the time.
6. **Speed is the parameter.** Ten helpers divide every speed by ten: with (5, 0.2) the take is
   `1 + (50 + 1 / (exp(0.02) - 1)) / m` = 20.9 limits, within 5%. The take is proportional to the number of
   shops the attacker can reach in the time news takes to get to the chain and back.

Failure would be: a take that grows in proportion to `M` in arms C or D; or a run in arm D' above the cap.

## Scope

The attacker visits shops in a random order and does not know which shops have heard. Shops in arm C are
honest relays. Carriers in arm D are not modelled as a market: `d` is given, and what reward buys what delay
is not examined. A shop's sync returns the chain's whole view at that moment. The payer is assumed to pay
nothing, so every note is a loss; whether the take is worth the payer's standing is `standing_value/`'s
question.
