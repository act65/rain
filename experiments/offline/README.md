# Offline: accepting a payment you cannot check

Started 2026-11-20. Serves the claim that Rain works where there is no connection, which is where it
started (the offline economy), and the design of `OfflineNoteScript` and `rain/offline.py`.

## Question

A payer with no connection signs a note. The payee cannot check the payer's balance, and the note reaches the
chain later. A payer can sign more than they hold: a double spend, which nothing can prevent while the parties
are disconnected (an available, partition-tolerant system cannot also be consistent). In Rain a note is a
promise, and one that is not paid is a broken promise.

1. How much should a payee accept from a payer, when other payees it cannot see may be accepting notes from the
   same payer?
2. What does being disconnected cost an honest payer, in credit now and in the rate at which credit grows?
3. Does reading notes that were owed at once as evidence of their total open a new way to manufacture a record?

Kind: deductive. Everything follows from the threshold belief of `rain/record.py`. The simulation checks the
formulas against the model of the contracts and against a population of payers drawn from the belief.

## Decision it feeds

What the reference payee does (`rain.offline.split_limit`), whether `rain.record.weigh` needs the `concurrent`
reading, and what the posts may claim about Rain offline.

## Setup

`Economy.current_rules` (fee 1%, minimum 0.1, point price 0.04, decay 0.03). The belief of `collusion/`:
thresholds Pareto with tail index 1 above a floor of 100, shocks 2%, a payee accepts a 10% chance of default.
A payer whose record shows `E` owed at once and paid has a limit `L = 1.089 E` (a stranger: 108.9).

**Payers.** Each has a threshold `c`, drawn from the belief given the record (`P(c > x) = E / x`), and takes
everything on offer. If the total they then owe is at most `c` and no shock hits, they pay every note;
otherwise none. 100,000 payers per cell, five seeds. An attacker is a payer who pays nothing.

**Payees.** `n` payees see the same payer between two syncs. Rules:

| arm | what each payee accepts |
|---|---|
| A (control) | the whole limit `L`, as if it were the only one |
| B | `L / m`: the limit divided by the number of places `m` the payer could be (`m` = 5) |
| C | whatever a local hub allows: every payee in a market asks one hub, which keeps the payer's running total and allows `L` in all. `k` hubs that cannot see each other |
| S | as B, with a log `s` syncs old, against a payer who has since defaulted on a lender on the chain |

**Growth.** An honest payer (never breaks a promise) starts as a stranger and for 30 windows spends what they
are allowed at `j` of `m` payees, every note paid at the sync. The payees then read the log two ways: the
default reading (the largest single promise kept) and `concurrent=True` (the largest total owed at once and
kept), trusting each other at `t`.

**Washing.** A borrower and `n` confederates issue notes at once, total `M`, and a bank that gives unknown
counterparties trust `t0` reads the log with `concurrent=True`. `M` over 41 values from 100 to 1e7,
`n` = 1, 2, 5.

Controls. Arm A must show payees losing more than they accepted (if payees who each lend the whole limit are
not over-exposed, the double spend is not implemented). With `n` = 1 every rule must give a 10% default rate.

## Predictions (written 2026-11-20, before running)

1. **Control: exposure multiplies with the number of payees.** In arm A an attacker takes `n L`, and the
   default rate among ordinary payers is `1 - 0.9 / n`: 10%, 55%, 82% and 91% for `n` = 1, 2, 5, 10 (each
   within 1 point).
2. **Dividing the limit restores it.** In arm B with `m` = 5 the default rate is 2% for `n` up to 4 (only
   shocks: the payer owes less than they have already shown), 10% at `n` = 5, and 55% at `n` = 10, where the
   payees underestimated `m` by half. An attacker takes `L n / m`: at most `L` while `n <= m`.
3. **A hub restores it without dividing.** With one hub the default rate is 10% and an attacker takes `L`,
   however many payees. With `k` hubs the results are arm A's with `n = k`.
4. **A stale log is one more place.** In arm S the defaulter takes `L` from the lender and a further
   `L n / m` from payees who have not seen it: `2 L` in all at `n = m`, whatever `s` is (once it is at least
   one sync).
5. **Under the default reading, credit does not grow offline.** With `m` >= 2 the honest payer's limit is
   108.9 after 30 windows as at the start: no single note is as large as what they had already shown.
6. **Under the concurrent reading it grows only for a payer who uses the whole limit.** With `t` = 1 and
   `j = m` = 5 the limit grows by 1.089 a window, as it would on a ladder of loans (to 100 x 1.089^31 = 1,404,
   within 1%). With `j` = 4 it does not grow at all (4/5 of 1.089 is less than 1).
7. **It needs payees who trust each other.** With `j = m` = 5 the growth per window is between 1.02 and 1.089
   at `t` = 0.9, and below 1.01 at `t` = 0.5: a total is only as credible as all its parts. Through one hub it
   is 1.089 a window whatever `j` is, provided the payer spends the limit.
8. **The concurrent reading gives a ring nothing.** For `t0` = 0, 0.5 and 0.9, the largest offer the ring
   extracts from a bank reading with `concurrent=True`, at any `n`, is no more than one confederate extracts
   under the default reading (1.00, 1.08 and 1.74 times a stranger's offer). Splitting a wash among
   confederates costs the same fees and is believed less.

Failure would be: a default rate above 10.5% in arm B with `n <= m`; an honest payer whose limit grows under
the default reading with `m` >= 2; or a ring that gains from the concurrent reading.

## Scope

The payer takes everything on offer and pays all or nothing. Payees know `m`; how they would estimate it (how
many payees a payer can reach between syncs) is not modelled, and prediction 2 shows what an underestimate
costs. Notes are not transferable. Secure hardware, which could enforce a spending cap on the payer's device,
is not assumed. The hub is trusted by its market to keep the running total; what it earns and whether it
answers for the notes (a guarantor, as in `vouching/`) is not modelled.

## Outcome (2026-11-20)

Numbers are in `results/SUMMARY.md`. Both controls behaved: payees who each accept the whole limit are
over-exposed in proportion to their number, and with one payee every rule gives a 10% default rate (9.97%).

| prediction | outcome |
|---|---|
| 1. control: default rate 10%, 55%, 82%, 91% for 1, 2, 5, 10 payees; an attacker takes `n L` | Held: 9.97%, 55.00%, 81.93%, 90.93%, and 1, 2, 5, 10 limits. |
| 2. dividing by 5: 2% up to four payees, 10% at five, 55% at ten | Held: 1.98%, 9.97%, 55.00%. An attacker takes a fifth of the limit per payee. |
| 3. one hub: 10% and one limit; `k` hubs as arm A | Held. |
| 4. a stale log is one more place: `2 L` in all at `n = m` | Held: 2.00 limits with five payees, 1.20 with one. Payees with a fresh log refuse a delinquent payer, and the total is 1.00. If lender and payees all divide by six the total is again one limit (arithmetic; the lender's smaller loan was not simulated). |
| 5. default reading: no growth offline with two or more payees | Held: 108.9 after 30 windows. |
| 6. concurrent reading, full trust: 1.089 a window at five of five payees, none at four of five | Held: 1,401 after 30 windows (I wrote 1,404; the arithmetic was mine), and 108.9 at four of five. |
| 7. growth between 1.02 and 1.089 a window at trust 0.9, below 1.01 at trust 0.5; a hub gives 1.089 | **Wrong at 0.9 in kind.** The first step is 1.057, and then growth stops: the limit settles at 126 (1.16 times a stranger's) and stays there. At trust 0.5 it settles at 109.5. Partial trust between payees does not slow the climb, it caps it. This is the collusion result again: a total five payees vouch for at 0.9 each is 59% credible, and no amount of repetition by the same five makes it more so. With two payees at 0.9 the cap is 188. Through one hub it is 1.089 a window, at two payees or five, as predicted. |
| 8. the concurrent reading gives a ring nothing | Held: 1.00, 1.06 and 1.40 times a stranger's offer with two confederates (1.24 with five), against 1.00, 1.08 and 1.73 for one confederate under the default reading. The default reading with five confederates treated as independent gives 3.5 and 8,140: the many-confederate attack of `collusion/`, which the concurrent reading does not suffer because it treats all counterparties as one group. |

What this shows:

- **A double spend is a default, and the limit that contains it is a credit limit on the whole payer.** The
  belief was always about everything a person owes at once. On a chain one lender sees it all. Offline each
  payee sees its own notes, so the exposure is the limit times the number of places that cannot see each other.
- **Dividing the limit by the number of places restores the 10%.** The price of being available while
  partitioned is a factor `m` in what any one payee will accept, and an underestimate of `m` by half costs a
  55% default rate.
- **A stale log is another place.** A payee who has not synced is exposed to whatever the payer did on the
  chain since.
- **Consistency inside the partition removes the factor.** A camp is cut off from the internet, not from
  itself. One hub that every payee in a market asks, over a local network, sees the whole payer: the limit is
  not divided, and an attacker takes one limit. The double spend that remains is between hubs.
- **Offline, standing is spent and hardly built**, unless notes owed at once are read as their total
  (`weigh(..., concurrent=True)`) by payees who trust each other fully, or who share a hub. Under the default
  reading a payer whose limit is divided never shows more than they already had. With the concurrent reading
  and five payees who trust each other at 0.9, credit stops at 1.16 times a stranger's.
- **The concurrent reading is safe to adopt**: it is never more confident than the default reading about a
  single amount, and splitting a wash among confederates is believed less than one wash of the same total.

What it does not show: how a payee should estimate `m`; what a hub earns or risks; what happens when notes are
passed on. The recommendation for a market without connection is a hub that answers for what it allows, which
is the guarantor of `vouching/` and has not been built for notes.
