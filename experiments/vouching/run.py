"""
Claim under test: a guarantee moves the lender's risk onto the guarantor's record; a lender who
counts guarantees against the guarantor's credit and counts only promises made to itself cannot
be robbed through guaranteed loans; and vouching costs the guarantor what they believe. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from rain.model import Economy
from rain.provenance import run_provenance
from rain.record import largest_amount_due, weigh

HERE = Path(__file__).parent
KAPPA, DELTA, R, PHI, FMIN, INTEREST = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05
FLOOR, TAIL, SHOCK = 100.0, 1.0, 0.02
BELIEF = dict(risk_tolerance=SHOCK + 1e-9, floor=FLOOR, tail_index=TAIL, shock_rate=SHOCK)  # no risk beyond shocks
KEEP = DELTA / (R + DELTA)
SAM_DUE = 10_000.0
HORIZON = 600
BANK_ONLY = {"bank": 1.0}


def fee(due):
    return max(FMIN, PHI * due)


def offer(log, who, trust):
    """The largest amount due the bank accepts from `who`."""
    return largest_amount_due(weigh(log, who, trust=trust).repaid, **BELIEF)


def world(sybils):
    """A steady economy in which Sam has already repaid 10,000 to the bank. Returns (economy, tick, ring)."""
    flow = 1e7
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=flow / KAPPA / DELTA)
    eco.add_agent("bank", money=1e12)
    ring = ["sam"] + [f"fake{j}" for j in range(sybils)]
    for name in ring:
        eco.add_agent(name, money=2e7)
    eco.start_in_steady_state(flow)
    eco.repay_loan(eco.loan("sam", "bank", SAM_DUE / (1 + INTEREST), SAM_DUE - SAM_DUE / (1 + INTEREST)))

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=flow / PHI)
    return eco, tick, ring


def present_value(eco, tick, ring, script):
    """Discounted change in the ring's money: `script(t)` acts in cycle t (0, 1), then the economy runs on."""
    def money():
        return math.fsum(eco.agents[n].money for n in ring)
    start, bank_start = money(), eco.agents["bank"].money
    script(0)
    pv = money() - start
    for t in range(1, HORIZON + 1):
        before = money()
        tick()
        if t == 1:
            script(1)
        pv += (money() - before) / (1 + R) ** t
    return pv - idle_value(ring), bank_start - eco.agents["bank"].money


_IDLE = {}


def idle_value(ring):
    """What the ring's members would collect anyway (dividends on Sam's earlier loan), so that results are net of it."""
    key = "sam" in ring
    if key not in _IDLE:
        eco, tick, _ = world(0)
        before, pv = eco.agents["sam"].money, 0.0
        for t in range(1, HORIZON + 1):
            tick()
            now = eco.agents["sam"].money
            pv += (now - before) / (1 + R) ** t
            before = now
        _IDLE[key] = pv if key else 0.0
    return _IDLE[key]


# --- A. manufacturing records through the guarantee ---

def arm_a(sybils, trust, wash=True):
    eco, tick, ring = world(sybils)
    line = offer(eco.log, "sam", BANK_ONLY)
    offers = []

    def script(t):
        for name in ring[1:]:
            if t == 0 and wash:
                eco.repay_loan(eco.guaranteed_loan(name, "sam", "bank", line / (1 + INTEREST), line - line / (1 + INTEREST)))
            if t == 1:
                due = offer(eco.log, name, trust)
                offers.append(due)
                eco.default_loan(eco.loan(name, "bank", due / (1 + INTEREST), due - due / (1 + INTEREST)))
    pv, bank_loss = present_value(eco, tick, ring, script)
    return dict(present_value=pv, bank_loss=bank_loss, offer=offers[0])


def formula_a(sybils, final_due, wash=True):
    cost = (SAM_DUE - SAM_DUE / (1 + INTEREST)) + 2 * fee(SAM_DUE) * (1 - KEEP) if wash else 0.0
    take = (final_due / (1 + INTEREST) - fee(final_due)) / (1 + R)
    return sybils * (take - cost)


# --- B. a guarantor who burns their standing ---

def arm_b(sybils, counted):
    eco, tick, ring = world(sybils)
    line = offer(eco.log, "sam", BANK_ONLY)
    loans = []

    def script(t):
        if t == 0:
            outstanding = 0.0
            for name in ring[1:]:
                due = min(line, line - outstanding) if counted else line
                if due <= 0:
                    continue
                outstanding += due
                loans.append(eco.guaranteed_loan(name, "sam", "bank", due / (1 + INTEREST), due - due / (1 + INTEREST)))
        if t == 1:
            for loan in loans:
                eco.default_loan(loan)
                eco.guarantor_default(loan)
    pv, bank_loss = present_value(eco, tick, ring, script)
    return dict(present_value=pv, bank_loss=bank_loss, loans=len(loans))


# --- C. what a vouch costs, and what it is worth ---

def vouch_cost(opportunist_belief, due=SAM_DUE):
    """Expected cost to the guarantor of one vouch: the chance of paying, times the amount, plus the net fee."""
    return (opportunist_belief + (1 - opportunist_belief) * SHOCK) * due + fee(due) * (1 - KEEP)


def simulate_vouch_cost(opportunist_share, n=2_000_000, seed=0, due=SAM_DUE):
    rng = np.random.default_rng(seed)
    pays = (rng.random(n) < opportunist_share) | (rng.random(n) < SHOCK)
    cost = np.where(pays, due, 0.0) + fee(due) * (1 - KEEP)
    return float(cost.mean()), float(cost.std() / np.sqrt(n))


def covered_loan_cost():
    """One vouch that goes wrong, in the model: what the guarantor is out, in present value."""
    eco, tick, ring = world(1)
    def script(t):
        if t == 0:
            loan = eco.guaranteed_loan("fake0", "sam", "bank", SAM_DUE / (1 + INTEREST), SAM_DUE - SAM_DUE / (1 + INTEREST))
            eco.default_loan(loan)
            eco.cover_loan(loan)
    ring_pv, bank_loss = present_value(eco, tick, ["sam"], script)
    return dict(guarantor_present_value=ring_pv, bank_loss=bank_loss)


def borrower_net(surplus_rate, due, price=0.0):
    """A genuine borrower's net gain per loan: what the money earns, less the net fee and the price of the vouch."""
    return surplus_rate * due / (1 + INTEREST) - fee(due) * (1 - KEEP) - price


def main():
    stranger = arm_a(1, BANK_ONLY, wash=False)
    base = stranger["present_value"]

    a = []
    for sybils in (1, 5):
        for name, trust in (("naive", None), ("sceptical", BANK_ONLY)):
            r = arm_a(sybils, trust)
            formula = formula_a(sybils, r["offer"])
            a.append(dict(fake_borrowers=sybils, bank=name, offer=r["offer"], present_value=r["present_value"],
                          formula=formula, gain_over_strangers=r["present_value"] - sybils * base,
                          gain_per_fake_borrower=(r["present_value"] - sybils * base) / sybils,
                          bank_loss=r["bank_loss"], relative_error=abs(r["present_value"] - formula) / abs(formula)))

    b = []
    for sybils in (1, 5, 20):
        for counted in (True, False):
            r = arm_b(sybils, counted)
            b.append(dict(fake_borrowers=sybils, guarantees_count_against_the_guarantor=counted, **r))

    c = []
    for belief in (0.0, 0.1, 0.5):
        mean, se = simulate_vouch_cost(belief)
        c.append(dict(opportunist_share=belief, formula=vouch_cost(belief), simulated=mean, standard_error=se))
    fair = vouch_cost(0.0)
    threshold = (1 + INTEREST) * (SHOCK + 2 * PHI * (1 - KEEP))
    worth = [dict(surplus_rate=s, with_guarantor=borrower_net(s, SAM_DUE, fair), alone=borrower_net(s, FLOOR))
             for s in (0.03, 0.0341, 0.06)]

    worst = max(r["relative_error"] for r in a)
    out = dict(provenance=run_provenance(),
               parameters=dict(kappa=KAPPA, delta=DELTA, r=R, fee_rate=PHI, min_fee=FMIN, interest=INTEREST, sam_due=SAM_DUE, **BELIEF),
               stranger=stranger, A=a, B=b, C=dict(vouch_cost=c, covered_loan=covered_loan_cost(), fair_price=fair,
                                                   surplus_threshold=threshold, borrower=worth),
               worst_relative_error=worst)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Vouching: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"A stranger is offered {stranger['offer']:.1f} due; defaulting on it is worth {base:.1f}.",
         f"Worst relative error, formula against simulation, in arm A: {worst:.1e}.", "",
         "## A. Fake borrowers who repay a guaranteed loan, then borrow alone and default", "",
         "| fake borrowers | bank | bank then offers each | ring's gain per fake borrower, over a stranger's | bank's loss |", "|---|---|---|---|---|"]
    L += [f"| {r['fake_borrowers']} | {r['bank']} | {r['offer']:,.0f} | {r['gain_per_fake_borrower']:+,.0f} | {r['bank_loss']:,.0f} |" for r in a]
    L += ["", "## B. The guarantor lets every guaranteed loan default and does not pay", "",
          "| fake borrowers | guarantees count against the guarantor's credit | loans made | bank's loss | ring's present value |", "|---|---|---|---|---|"]
    L += [f"| {r['fake_borrowers']} | {'yes' if r['guarantees_count_against_the_guarantor'] else 'no (control)'} | {r['loans']} | {r['bank_loss']:,.0f} | {r['present_value']:,.0f} |" for r in b]
    L += ["", "## C. What a vouch for 10,000 costs the guarantor", "",
          "| share of applicants who are opportunists | expected cost (formula) | simulated | standard error |", "|---|---|---|---|"]
    L += [f"| {100 * r['opportunist_share']:.0f}% | {r['formula']:,.1f} | {r['simulated']:,.1f} | {r['standard_error']:.1f} |" for r in c]
    cov = out["C"]["covered_loan"]
    L += ["", f"One vouch that goes wrong, in the model: the guarantor is out {-cov['guarantor_present_value']:,.1f} and the bank loses {cov['bank_loss']:,.1f}.",
          "", f"A genuine borrower, paying the fair price of {fair:,.1f} per loan (worth buying above a surplus of {100 * threshold:.2f}%):", "",
          "| surplus per loan | net per loan with a guarantor (10,000) | net per loan alone (100) |", "|---|---|---|"]
    L += [f"| {100 * r['surplus_rate']:.2f}% | {r['with_guarantor']:+,.1f} | {r['alone']:+,.2f} |" for r in worth]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
