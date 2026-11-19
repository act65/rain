"""
Claim under test: with `rain.record.graduated_credit` a lender can let a record made under a
guarantee (or with anyone) count towards unsecured credit, no ring can profit from manufacturing
one, and an honest newcomer outgrows their guarantor. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from rain.model import Economy
from rain.provenance import run_provenance
from rain.record import graduated_credit

HERE = Path(__file__).parent
KAPPA, DELTA, R, PHI, FMIN, INTEREST, SHOCK = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05, 0.02
START, SAM_DUE, NEED = 100.0, 10_000.0, 10_000.0
KEEP = DELTA / (R + DELTA)
SUNK = 1 - KEEP
GROWTH = 1 + INTEREST
TAIL = 400  # cycles simulated after the last action, to collect dividends
RING = ["sam", "fake", "friend"]


# --- the bank's rules ---

def kept_by(log, who):
    return [e for e in log if e.promisor == who and e.kept]


def rule_graduated(log, who):
    return graduated_credit(log, who, "bank", START, GROWTH, SUNK)


def rule_evidence_alone(log, who):
    return max([START] + [e.amount for e in kept_by(log, who)])


def rule_no_growth_limit(log, who):
    kept = kept_by(log, who)
    evidence = max([START] + [e.amount for e in kept])
    if any(e.promisee == "bank" for e in kept):
        return evidence
    return min(evidence, START + SUNK * sum(e.fee_paid for e in kept))


def rule_cost_every_time(log, who):
    kept = kept_by(log, who)
    evidence = max([START] + [e.amount for e in kept])
    own = max([0.0] + [e.amount for e in kept if e.promisee == "bank"])
    return min(evidence, (GROWTH * own if own else START) + SUNK * sum(e.fee_paid for e in kept))


RULES = {"graduated": rule_graduated, "evidence alone": rule_evidence_alone,
         "no growth limit": rule_no_growth_limit, "cost counted every time": rule_cost_every_time}


# --- the economy ---

def world():
    flow = 1e7
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=flow / KAPPA / DELTA)
    eco.add_agent("bank", money=1e12)
    for name in RING + ["newcomer"]:
        eco.add_agent(name, money=2e7)
    eco.start_in_steady_state(flow)
    eco.repay_loan(eco.loan("sam", "bank", SAM_DUE / GROWTH, SAM_DUE - SAM_DUE / GROWTH))  # Sam's standing

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=flow / PHI)
    return eco, tick


def bank_loan(eco, who, due):
    return eco.loan(who, "bank", due / GROWTH, due - due / GROWTH)


def run(act, cycles, who=RING):
    """Present value of the change in `who`'s money when `act(eco, t)` is called in cycles 0..cycles, then nothing."""
    eco, tick = world()

    def money():
        return math.fsum(eco.agents[n].money for n in who)
    pv = 0.0
    for t in range(cycles + 1 + TAIL):
        before = money()
        if t > 0:
            tick()
        if t <= cycles:
            act(eco, t)
        pv += (money() - before) / (1 + R) ** t
    return pv, eco


IDLE = run(lambda eco, t: None, 0)[0]  # the dividends Sam collects anyway


def attack(rule, variant, amount, last):
    """
    The ring's present value, net of doing nothing. The fake borrower makes a record by `variant`
    with `amount`, borrows the bank's unsecured offer every cycle up to `last`, and defaults on that one.
    """
    offer = RULES[rule]
    state = dict(own=None, guaranteed=None, offers=[])

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
        due = offer(eco.log, "fake")
        state["offers"].append(due)
        state["own"] = bank_loan(eco, "fake", due)
    pv, _ = run(act, last + 1)
    return pv - IDLE, state["offers"]


STRATEGIES = [("none", 0.0)] + [(f"guaranteed, {when}", x) for when in ("once", "every cycle") for x in (1e3, 1e4)] \
    + [(f"wash, {when}", x) for when in ("once", "every cycle") for x in (1e3, 1e4, 1e5)]


def search(rule, lasts):
    best, rows = None, []
    for variant, amount in STRATEGIES:
        for last in lasts:
            pv, offers = attack(rule, variant, amount, last)
            row = dict(variant=variant, amount=amount, defaults_on_loan=last, gain=pv - STRANGER, final_offer=offers[-1])
            rows.append(row)
            if best is None or row["gain"] > best["gain"]:
                best = row
    return best, rows


# --- the honest newcomer ---

def newcomer(with_guarantor, cycles=80):
    state = dict(own=None, guaranteed=None, offers=[], guaranteed_amounts=[])

    def act(eco, t):
        for key in ("guaranteed", "own"):
            if state[key] is not None:
                eco.repay_loan(state[key])
                state[key] = None
        own = min(NEED, rule_graduated(eco.log, "newcomer"))
        # The first guaranteed loan is for the whole amount, so that the record shows what they can carry.
        rest = (NEED if t == 0 else NEED - own) if with_guarantor else 0.0
        state["offers"].append(own)
        state["guaranteed_amounts"].append(rest)
        state["own"] = bank_loan(eco, "newcomer", own)
        if rest > 1e-6:
            state["guaranteed"] = eco.guaranteed_loan("newcomer", "sam", "bank", rest / GROWTH, rest - rest / GROWTH)
    run(act, cycles, who=["newcomer"])
    offers, guaranteed = state["offers"], state["guaranteed_amounts"]
    graduated = next((t for t, g in enumerate(guaranteed) if g <= 1e-6), None) if with_guarantor else None
    vouch_cost = sum(((1 - SHOCK) / (1 + R)) ** t * (SHOCK * g + max(FMIN, PHI * g) * SUNK) for t, g in enumerate(guaranteed) if g > 1e-6)
    return dict(offers=offers[:60], guaranteed=guaranteed[:60], cycles_to_graduate=graduated, guarantor_expected_cost=vouch_cost)


def main():
    global STRANGER
    STRANGER, _ = attack("graduated", "none", 0.0, 0)

    # 1. what a guaranteed loan outstanding for a cycle costs the ring
    def one_round(eco, t):
        if t == 0:
            one_round.loan = eco.guaranteed_loan("fake", "sam", "bank", SAM_DUE / GROWTH, SAM_DUE - SAM_DUE / GROWTH)
        if t == 1:
            eco.repay_loan(one_round.loan)
    p1 = dict(simulated_cost=-(run(one_round, 1)[0] - IDLE), fees_sunk=2 * PHI * SAM_DUE * SUNK)

    # 2. the search under the rule
    best, rows = search("graduated", range(0, 61))
    manufacturing = [r for r in rows if r["variant"] != "none"]
    p2 = dict(strategies=len(rows), best=best, best_that_manufactures_a_record=max(manufacturing, key=lambda r: r["gain"]),
              worst=min(rows, key=lambda r: r["gain"]),
              best_by_variant={f"{v} {x:,.0f}": max(r["gain"] for r in rows if (r["variant"], r["amount"]) == (v, x)) for v, x in STRATEGIES})

    # 3. the controls
    p3 = {}
    for rule in ("evidence alone", "no growth limit", "cost counted every time"):
        b, control_rows = search(rule, [0, 1, 2, 5, 20, 40])
        by_last = {str(last): max(r["gain"] for r in control_rows if r["defaults_on_loan"] == last) for last in (0, 1, 2, 5, 20, 40)}
        p3[rule] = dict(best=b, best_gain_by_last_loan=by_last)

    # 4. the honest newcomer
    with_g, alone = newcomer(True), newcomer(False)
    recurrence, t = 162.5, 0
    while recurrence < NEED:
        recurrence, t = GROWTH * recurrence + 62.5, t + 1
    p4 = dict(with_guarantor=with_g, alone=dict(offers=alone["offers"][:10]), cycles_by_recurrence=t)

    # 5. what a point is worth as first-rung credit
    eco, _ = world()
    eco.repay_loan(eco.loan("fake", "friend", 10_000.0, 0.0))
    points = eco.agents["fake"].reputation
    p5 = dict(points=points, offer=rule_graduated(eco.log, "fake"), credit_per_point=(rule_graduated(eco.log, "fake") - START) / points,
              predicted=KAPPA * SUNK)

    out = dict(provenance=run_provenance(),
               parameters=dict(kappa=KAPPA, delta=DELTA, r=R, fee_rate=PHI, interest=INTEREST, start=START, sunk_fee_share=SUNK),
               stranger=STRANGER, one_guaranteed_round=p1, rule=p2, controls=p3, newcomer=p4, per_point=p5)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Graduation: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"A stranger's default is worth {STRANGER:.2f}.",
         f"One guaranteed loan of 10,000, outstanding a cycle and repaid, costs the ring {p1['simulated_cost']:.1f} (fees sunk: {p1['fees_sunk']:.1f}).", "",
         "## The rule: best gain over a stranger's default, by strategy (defaulting on any loan from the 1st to the 61st)", "",
         "| record made by | amount | best gain |", "|---|---|---|"]
    L += [f"| {v} | {x:,.0f} | {p2['best_by_variant'][f'{v} {x:,.0f}']:+,.2f} |" for v, x in STRATEGIES]
    L += ["", f"{p2['strategies']} strategies searched. Best: {best['variant']} (gain {best['gain']:+.2f}). "
          f"Worst: {p2['worst']['variant']} of {p2['worst']['amount']:,.0f}, defaulting on loan {p2['worst']['defaults_on_loan'] + 1} ({p2['worst']['gain']:+,.0f}).", "",
          "## Controls: the ring's best gain under weaker rules", "",
          "| rule | best strategy | gain | best gain defaulting on loan 1, 2, 3, 6, 21, 41 |", "|---|---|---|---|"]
    for rule, r in p3.items():
        b = r["best"]
        seq = ", ".join(f"{g:+,.0f}" for g in r["best_gain_by_last_loan"].values())
        L.append(f"| {rule} | {b['variant']} of {b['amount']:,.0f}, default on loan {b['defaults_on_loan'] + 1} | {b['gain']:+,.0f} | {seq} |")
    g = with_g
    L += ["", "## An honest newcomer who needs 10,000 a cycle", "",
          f"With a guarantor: unsecured offer {', '.join(f'{x:,.0f}' for x in g['offers'][:6])}, ... ; "
          f"the guaranteed part reaches zero in cycle {g['cycles_to_graduate']} (recurrence: {t}). "
          f"Expected cost to the guarantor over that time: {g['guarantor_expected_cost']:,.0f}.",
          f"Alone: unsecured offer {', '.join(f'{x:,.0f}' for x in alone['offers'][:6])}, ...", "",
          "| cycle | unsecured | guaranteed |", "|---|---|---|"]
    L += [f"| {c} | {g['offers'][c]:,.0f} | {g['guaranteed'][c]:,.0f} |" for c in (0, 1, 5, 10, 20, 30, 40, 45, 50) if c < len(g["offers"])]
    L += ["", f"## Credit per reputation point", "",
          f"{p5['points']:,.0f} points earned by washing: offered {p5['offer']:.2f}, i.e. {p5['credit_per_point']:.4f} per point (predicted {p5['predicted']:.4f})."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


STRANGER = 0.0

if __name__ == "__main__":
    main()
