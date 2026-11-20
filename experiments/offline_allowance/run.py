"""
Claim under test: an allowance backed by locked funds does not change the race between a double spender
and the news, but it takes one limit off what shops lose, makes payers who stay within it certain to pay,
turns the float into a deterrent in proportion to the attacker's speed, and cannot be used to frame an
honest payer. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
KAPPA, DELTA, PHI, FMIN = 0.04, 0.03, 0.01, 0.0
M, GUESS, DELAY, SYNC = 1_000, 5, 5, 0.2
A = 1_000.0  # the allowance, in currency; results are reported in units of it
NOTE = A / GUESS
SEEDS = 20
SHOCK, RISK = 0.02, 0.10


def race(seed, helpers=1, expires=None, certificate=True):
    """
    Notes the attacker gets accepted. A shop's last sync showed `seen` of the attacker's notes on the chain.
    With a certificate it refuses when those and the new note would exceed the allowance; without one it
    refuses when they already total the limit it worked out for this payer (the same amount here).
    """
    rng = np.random.default_rng(seed)
    on_chain_at, accepted = [], 0
    for step in range(1, M + 1):
        now = step / helpers
        if expires is not None and now > expires:
            break
        since_sync = rng.exponential(1 / SYNC)
        seen = sum(1 for t in on_chain_at if t <= now - since_sync)
        refuse = (seen * NOTE + NOTE > A + 1e-9) if certificate else (seen * NOTE >= A - 1e-9)
        if not refuse:
            accepted += 1
            on_chain_at.append(now + DELAY)
    return accepted


def stats(values):
    values = np.asarray(values, dtype=float)
    return dict(mean=float(values.mean()), standard_error=float(values.std(ddof=1) / math.sqrt(len(values))))


def race_formula(helpers=1):
    return 1 + (DELAY * helpers + 1 / (math.exp(SYNC / helpers) - 1)) / GUESS


# --- what shops lose, through the model of the contracts ---

def economy(shops):
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("payer", money=10 * A)
    for i in range(shops):
        eco.add_agent(f"shop{i}", money=10 * A)
    return eco


def shops_loss(notes, locked):
    """What `notes` shops lose in all to a payer who pays nothing in person: goods handed over, less money received."""
    eco = economy(notes)
    start = sum(eco.agents[f"shop{i}"].money for i in range(notes))
    if locked:
        allowance = eco.open_allowance("payer", A)
    eco.agents["payer"].money = 0.0
    for i in range(notes):
        if locked:
            eco.present_allowance_note(allowance, f"shop{i}", NOTE)
        else:
            eco.settle_note("payer", f"shop{i}", NOTE)
    received = sum(eco.agents[f"shop{i}"].money for i in range(notes)) - start
    return (notes * NOTE - received) / A


def ordinary_payers(n=2_000, seed=0):
    """Share of notes left unpaid by payers who spend their allowance at five shops, some of whom are then hit by a shock."""
    rng = np.random.default_rng(seed)
    unpaid = {"locked": 0, "plain": 0}
    for hit in rng.random(n) < SHOCK:
        for kind in unpaid:
            eco = economy(GUESS)
            if kind == "locked":
                allowance = eco.open_allowance("payer", A)
            if hit:
                eco.agents["payer"].money = 0.0  # whatever the shock was, the payer's own account is empty
            for i in range(GUESS):
                paid = (eco.present_allowance_note(allowance, f"shop{i}", NOTE) if kind == "locked"
                        else eco.settle_note("payer", f"shop{i}", NOTE))
                unpaid[kind] += not paid
    return {kind: count / (n * GUESS) for kind, count in unpaid.items()}


# --- a shop that lies ---

def shut_out(rate, by, seed, believe=True):
    """Share of shops refusing an honest payer at time `by`, after one shop starts saying the payer has overspent."""
    if not believe:
        return 0.0  # there are no notes that total more than the allowance, so there is nothing to show a shop that checks
    rng = np.random.default_rng(seed)
    heard = np.zeros(M, dtype=bool)
    heard[0] = True
    for _ in range(by):
        for i in np.flatnonzero(heard):
            for other in rng.integers(0, M, size=rng.poisson(rate)):
                heard[other] = True
    return float(heard.mean())


def main():
    seeds = range(SEEDS)
    alone = [race(s) for s in seeds]
    without = [race(s, certificate=False) for s in seeds]
    helped = [race(s, helpers=10) for s in seeds]
    T = 10
    out = dict(provenance=run_provenance(),
               parameters=dict(market=M, guess=GUESS, delay=DELAY, sync_rate=SYNC, seeds=SEEDS, fee_rate=PHI, expiry=T))
    out["race"] = dict(with_certificate=stats(np.array(alone) / GUESS), without=stats(np.array(without) / GUESS),
                       identical_run_by_run=alone == without, formula=race_formula(), ten_helpers=stats(np.array(helped) / GUESS),
                       ten_helpers_formula=race_formula(10))
    out["expiry"] = dict(alone=stats(np.array([race(s, expires=T) for s in seeds]) / GUESS),
                         ten_helpers=stats(np.array([race(s, helpers=10, expires=T) for s in seeds]) / GUESS),
                         cap_alone=T / GUESS, cap_ten_helpers=10 * T / GUESS)
    out["loss"] = dict(plain=stats([shops_loss(n, locked=False) for n in alone]), locked=stats([shops_loss(n, locked=True) for n in alone]))
    out["ordinary_payers_unpaid"] = ordinary_payers()
    out["float"] = {str(f): dict(alone=float(np.mean(alone)) / GUESS - 1 - f, ten_helpers=float(np.mean(helped)) / GUESS - 1 - f)
                    for f in (0, 1, 2, 5)}
    by = round(2 * math.log(M))
    out["liars"] = dict(by=by, believing_hearsay=stats([shut_out(1.0, by, s) for s in seeds]),
                        checking_notes=stats([shut_out(1.0, by, s, believe=False) for s in seeds]))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p, r, e, l = out["provenance"], out["race"], out["expiry"], out["loss"]
    cell = lambda x: f"{x['mean']:.2f} ({x['standard_error']:.2f})"
    L = ["# Offline, an allowance backed by locked funds: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"Amounts are in units of the allowance. {M:,} shops, each accepting a fifth; a note reaches the chain after {DELAY}; "
         f"a shop syncs {SYNC} times per unit of time. Means over {SEEDS} seeds, standard errors in brackets.", "",
         "| | alone | ten helpers |", "|---|---|---|",
         f"| taken, with a certificate | {cell(r['with_certificate'])} | {cell(r['ten_helpers'])} |",
         f"| taken, without one | {cell(r['without'])} (the same run by run: {r['identical_run_by_run']}) | |",
         f"| formula | {r['formula']:.2f} | {r['ten_helpers_formula']:.2f} |",
         f"| taken when the certificate lasts {T} | {cell(e['alone'])} | {cell(e['ten_helpers'])} |",
         f"| reachable in that time | {e['cap_alone']:.2f} | {e['cap_ten_helpers']:.2f} |", "",
         f"Shops' loss to an attacker alone: {cell(l['plain'])} with plain notes, {cell(l['locked'])} with locked funds (fees of {100 * PHI:.0f}% included).", "",
         f"Notes left unpaid by payers who stay within the allowance, {100 * SHOCK:.0f}% of whom lose everything else: "
         f"{100 * out['ordinary_payers_unpaid']['locked']:.2f}% with locked funds, {100 * out['ordinary_payers_unpaid']['plain']:.2f}% with plain notes.", "",
         "| float, in allowances | attacker's gain alone | with ten helpers |", "|---|---|---|"]
    L += [f"| {f} | {g['alone']:+.2f} | {g['ten_helpers']:+.2f} |" for f, g in out["float"].items()]
    L += ["", f"A shop that says an honest payer has overspent: after {by} units of time {100 * out['liars']['believing_hearsay']['mean']:.1f}% of shops that believe hearsay "
          f"refuse the payer, and {100 * out['liars']['checking_notes']['mean']:.0f}% of shops that act only on notes they can check."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
