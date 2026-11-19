"""
Claim under test: `graduated_credit` credits fees as sunk at the lender's discount rate, so a more
patient ring can profit from it; setting the sunk share for the most patient attacker allowed for
removes the profit, and at a share of zero the newcomer still graduates, more slowly. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from rain.model import Economy
from rain.provenance import run_provenance
from rain.record import Entry, graduated_credit

HERE = Path(__file__).parent
KAPPA, DELTA, PHI, FMIN, INTEREST = 0.04, 0.03, 0.01, 0.1, 0.05
START, SAM_DUE, NEED = 100.0, 10_000.0, 10_000.0
GROWTH = 1 + INTEREST
TAIL = 600
RING = ["sam", "fake", "friend"]
RING_RATES = [0.05, 0.04, 0.03, 0.02, 0.01, 0.0]
ASSUMED = [0.05, 0.02, 0.0]  # the least an attacker is assumed to discount at
LASTS = [0, 1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 90, 120, 150]
STRATEGIES = [("none", 0.0)] + [(f"guaranteed, {when}", x) for when in ("once", "every cycle") for x in (1e3, 1e4)] \
    + [(f"wash, {when}", x) for when in ("once", "every cycle") for x in (1e3, 1e4, 1e5)]


def sunk_share(assumed_rate):
    return assumed_rate / (assumed_rate + DELTA)


def world():
    flow = 1e7
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=flow / KAPPA / DELTA)
    eco.add_agent("bank", money=1e12)
    for name in RING:
        eco.add_agent(name, money=2e7)
    eco.start_in_steady_state(flow)
    eco.repay_loan(eco.loan("sam", "bank", SAM_DUE / GROWTH, SAM_DUE - SAM_DUE / GROWTH))

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=flow / PHI)
    return eco, tick


def cash_flows(act, cycles):
    """The ring's net cash in each cycle."""
    eco, tick = world()
    flows = []
    for t in range(cycles + 1 + TAIL):
        before = math.fsum(eco.agents[n].money for n in RING)
        if t > 0:
            tick()
        if t <= cycles:
            act(eco, t)
        flows.append(math.fsum(eco.agents[n].money for n in RING) - before)
    return flows


def attack_flows(share, variant, amount, last):
    state = dict(own=None, guaranteed=None)

    def act(eco, t):
        if state["guaranteed"] is not None:
            eco.repay_loan(state["guaranteed"])
            state["guaranteed"] = None
        if state["own"] is not None:
            (eco.default_loan if t == last + 1 else eco.repay_loan)(state["own"])
            state["own"] = None
        if t > last:
            return
        if variant.startswith("guaranteed") and (t == 0 or variant.endswith("every cycle")):
            state["guaranteed"] = eco.guaranteed_loan("fake", "sam", "bank", amount / GROWTH, amount - amount / GROWTH)
        if variant.startswith("wash") and (t == 0 or variant.endswith("every cycle")):
            eco.repay_loan(eco.loan("fake", "friend", amount, 0.0))
        due = graduated_credit(eco.log, "fake", "bank", START, GROWTH, share)
        state["own"] = eco.loan("fake", "bank", due / GROWTH, due - due / GROWTH)
    return cash_flows(act, last + 1)


def present_value(flows, rate, idle):
    return sum((f - (idle[t] if t < len(idle) else 0.0)) / (1 + rate) ** t for t, f in enumerate(flows))


def graduation_cycles(share, cycles=200):
    log = []
    for t in range(cycles):
        own = min(NEED, graduated_credit(log, "newcomer", "bank", START, GROWTH, share))
        rest = NEED if t == 0 else NEED - own
        if rest <= 1e-6:
            return t
        log.append(Entry("newcomer", "sam", rest, True, time=t + 1, fee_paid=PHI * rest, created=t))
        log.append(Entry("newcomer", "bank", own, True, time=t + 1, fee_paid=PHI * own, created=t))
    return None


def main():
    idle = cash_flows(lambda eco, t: None, max(LASTS) + 1)
    results = {}
    for assumed in ASSUMED:
        share = sunk_share(assumed)
        runs = {(v, x, last): attack_flows(share, v, x, last) for v, x in STRATEGIES for last in LASTS}
        stranger = runs[("none", 0.0, 0)]
        by_rate = {}
        for rate in RING_RATES:
            base = present_value(stranger, rate, idle)
            gains = {key: present_value(flows, rate, idle) - base for key, flows in runs.items()}
            key = max(gains, key=gains.get)
            fees = PHI * key[1] * (1 if key[0].endswith("once") else key[2] + 1) * (2 if key[0].startswith("guaranteed") else 1)
            by_rate[str(rate)] = dict(best_gain=gains[key], strategy=key[0], amount=key[1], defaults_on_loan=key[2] + 1,
                                      gain_over_fees_paid=gains[key] / fees if fees else 0.0)
        results[str(assumed)] = dict(sunk_share=share, strategies=len(runs), by_ring_rate=by_rate,
                                     graduation_cycles=graduation_cycles(share))

    out = dict(provenance=run_provenance(), parameters=dict(kappa=KAPPA, delta=DELTA, fee_rate=PHI, interest=INTEREST), results=results)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# A patient ring: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         "The ring's best gain over a stranger's default, by its own discount rate (rows) and the sunk share the lender uses (columns).",
         f"{results['0.05']['strategies']} strategies per column.", "",
         "| ring discounts at | " + " | ".join(f"lender assumes at least {100 * a:.0f}% (share {results[str(a)]['sunk_share']:.3f})" for a in ASSUMED) + " |",
         "|---|" + "---|" * len(ASSUMED)]
    for rate in RING_RATES:
        cells = []
        for a in ASSUMED:
            r = results[str(a)]["by_ring_rate"][str(rate)]
            cells.append(f"{r['best_gain']:+,.1f}" + (f" ({r['strategy']} of {r['amount']:,.0f}, default on loan {r['defaults_on_loan']}; {100 * r['gain_over_fees_paid']:.1f}% of fees)" if r["best_gain"] > 1e-6 else ""))
        L.append(f"| {100 * rate:.0f}% | " + " | ".join(cells) + " |")
    L += ["", "Cycle in which an honest newcomer needs no guarantor: " +
          ", ".join(f"share {results[str(a)]['sunk_share']:.3f}: {results[str(a)]['graduation_cycles']}" for a in ASSUMED) + "."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
