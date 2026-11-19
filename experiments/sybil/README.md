# Sybil identities and vouching

> **This experiment studies the original rules** (flat reward, fee keeper, yield-only treasury, no decay), which the
> contracts no longer use. Its findings are part of why they changed. For the same question under the current
> rules see `../current_rules/`.

Started 2026-11-19. Serves the blog's Layer 2 ("Trust in the Actor") and the "Net-Negative Identity
Postulate" in `old/security.md`: creating an identity should cost more than can be extracted from it.

## Question

Exclusion and lost reputation only deter someone who cannot simply start again. What does a disposable
identity cost, and what can it extract, under each way an identity can come to hold reputation?

| scenario | how the identity gets reputation |
|---|---|
| S1 free mint | the admin mints 100 points to each new identity (what `scripts/deploy.py` does) |
| S2 bought | no free mint; the identity buys 100 points by keeping 4 wash promises with a partner |
| S3 vouched | no free mint; a sponsor the attacker controls bonds 100 of its own points for the recruit, forfeited if the recruit defaults |

Each is evaluated against a naive lender (the demo's 20 DMD per bonded point) and a careful one
(`0.9 * v` per point). Vouching is not implemented in the contracts; S3 models the scheme described in the notes.

Kind: deductive for the per-identity numbers; the scaling arm is a simulation with the fee keeper running.

## Decision it feeds

Whether new identities can be given any starting reputation, what an identity must cost, and whether
vouching changes the answer.

## Setup

Per identity: `Economy` as in `exit_scam/` (`v = 0.3077`). Profit is measured against never creating the
identity. For S1 the alternative use of the identity is also reported: keep it and collect dividends.

Scaling: an honest bloc (10,000 points, 100 kept promises per cycle) runs for 50 cycles with the keeper on.
Then `N` identities each buy 100 points (S2), borrow from a lender and default, all within one cycle, for
`N` in 1, 10, 100, 1000. Honest holders' dividend per point in the following cycle is compared with a run
without the attack.

## Predictions (written 2026-11-19, before running)

1. S1, naive lender: each identity extracts `20 * 100` minus one fee, about 2000 DMD. Careful lender: about
   `0.9 * v * 100` = 27.7 DMD. Simply holding the free points is worth `v * 100` = 30.8 DMD. All positive: a
   free mint is exploitable whatever lenders do, and an identity must cost at least `max(ell, v) * R0`.
2. S2: profit is `100 * (ell - m * v)` minus the scam fee: about 1954 DMD against the naive lender, and
   negative (about -18.5) against the careful one. The fee is the price of an identity.
3. S3: profit per recruit is `100 * (ell - v)` minus the fee, counting the sponsor's lost dividends: about
   1969 DMD naive, negative (about -3.1) careful. Vouching moves credit from sponsor to recruit; it does not
   create any.
4. Scaling, naive lender: profit per identity is the same for every `N` within 1% (the fee is fixed within a
   cycle), so the attack scales linearly. Careful lender (lending against `v` as it stands when the loan is
   made): profit is negative for every `N`.
5. Honest holders are not harmed: after the defaults the sybils' reputation is destroyed and the treasury
   has grown by their fees, so honest dividend per point in the next cycle is higher than without the
   attack. The lenders bear the whole loss.

Failure would be: a scenario where the careful lender loses, or honest holders' dividends fall.

## Scope

The cost of obtaining an identity outside the protocol (proof of personhood, etc.) is zero here; it adds
linearly. Lenders do not react during the attack.

## Outcome (2026-11-19)

Numbers are in `results/SUMMARY.md`.

| prediction | outcome |
|---|---|
| 1. S1 (free mint): about 2000 naive, 27.7 careful, 30.8 for just holding | Sign held; two numbers were off. Naive 1988.46, careful **16.15**, holding 30.77. I left the fee on the loan (11.54 DMD) out of the careful figure. |
| 2. S2 (bought): about 1954 naive, about -18.5 careful | Sign held; both numbers off by the same omitted fee: 1942.31 and **-30.00**. |
| 3. S3 (vouched): about 1969 naive, about -3.1 careful | Sign held; again off by one fee: 1957.69 and **-14.62**. |
| 4. scaling: constant profit per identity (naive); negative for every N (careful) | Held: 2000 DMD per identity at every N; -0.0008 to -0.0010 against the careful lender. |
| 5. honest holders are not harmed | Held: their dividend per point in the next cycle is higher by 0.01% (N = 1) to 11% (N = 1000). |

In every scenario the simulated profit equals the formula; the errors were in the figures I wrote down beforehand.

What this shows:

- **Free starting reputation is exploitable whatever lenders do.** Against a careful lender a free 100-point
  identity still nets 16 DMD from one loan, and simply holding it collects 31 DMD of dividends. Minting
  reputation to new identities, as the deploy script does, is a subsidy to whoever creates the most identities.
- **The fee is the price of an identity**, and it is the only one. Bought reputation costs `m v` per point, so a
  lender who advances less than that per point cannot lose to bought identities.
- **Vouching does not create credit, it moves it.** A sponsor's bonded point is worth `v` to the sponsor, so a
  lender who advances less than `v` against a vouch is safe, and one who advances more is paying the sponsor to
  burn reputation. It solves cold start for honest newcomers only by spending an existing user's capacity.
- **A sybil attack on lenders is good for holders.** The attackers' reputation is destroyed when they default
  and their fees stay in the treasury. The lenders bear the whole loss (2,000,000 DMD at N = 1000).
- **At the keeper's own fee an identity costs almost nothing.** In the running economy the fee has fallen to
  0.0003 DMD (see `fee_dynamics/`), so 100 points cost 0.0012 DMD and a careful lender advances 0.000007 DMD per
  point. Naive lenders are defenceless and careful lenders lend nothing.
