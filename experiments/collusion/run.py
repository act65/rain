"""
Claim under test: a record manufactured with confederates costs 0.625% of its face value, robs a
lender who believes the whole log, and gains nothing from a lender who gives unknown counterparties
no trust; any positive trust in unknown counterparties is unbounded exposure once identities are
free. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from rain.model import Economy
from rain.provenance import run_provenance
from rain.record import largest_amount_due, trusting, weigh

HERE = Path(__file__).parent
KAPPA, DELTA, R, PHI, FMIN, INTEREST = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05
RHO, FLOOR, TAIL, SHOCK = 0.10, 100.0, 1.0, 0.02
BELIEF = dict(risk_tolerance=RHO, floor=FLOOR, tail_index=TAIL, shock_rate=SHOCK)
P0 = (1 - RHO) / (1 - SHOCK)
KEEP = DELTA / (R + DELTA)  # share of a fee that comes back as dividends
AMOUNTS = [float(x) for x in np.logspace(2, 7, 41)]
CONFEDERATES = [0, 1, 2, 5, 10, 20]
HORIZON = 600


# --- the bank ---

def offer(log, borrower, trust, group=None):
    """The largest amount due the bank will accept from `borrower`, given the log and whom the bank trusts."""
    return largest_amount_due(weigh(log, borrower, trust=trust, group=group).repaid, **BELIEF)


STRANGER_DUE = largest_amount_due((), **BELIEF)


# --- the simulation ---

def world(fee_flow=1e7):
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=fee_flow / KAPPA / DELTA)
    eco.add_agent("bank", money=1e12)
    eco.start_in_steady_state(fee_flow)

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=fee_flow / PHI)
    return eco, tick


def simulate_attack(amount, n, trust, group=None, borrow=True):
    """
    Present value, to Mallory and the confederates together, of washing `amount` with each of `n`
    confederates in cycle 0 and (if `borrow`) defaulting on the bank's largest offer in cycle 1.
    Returns (present value, amount due the bank accepted).
    """
    eco, tick = world()
    ring = ["mallory"] + [f"friend{j}" for j in range(n)]
    for name in ring:
        eco.add_agent(name, money=2e7)  # enough to lend the largest amount, small enough to keep precision

    def money():
        return math.fsum(eco.agents[name].money for name in ring)

    start = money()
    for friend in ring[1:]:
        eco.repay_loan(eco.loan("mallory", friend, amount, 0.0))
    pv, due = money() - start, 0.0
    for t in range(1, HORIZON + 1):
        before = money()
        tick()
        if t == 1 and borrow:
            due = offer(eco.log, "mallory", trust, group)
            principal = due / (1 + INTEREST)
            eco.default_loan(eco.loan("mallory", "bank", principal, due - principal))
        pv += (money() - before) / (1 + R) ** t
    return pv, due


# --- the formulas ---

def wash_cost(amount, n=1):
    """Fees on `n` washes of `amount`, less the dividends the reputation they buy will collect."""
    return n * max(FMIN, PHI * amount) * (1 - KEEP)


def predicted_profit(amount, n, trust_in_unknown, grouped=False):
    """The attack's present value: the bank's principal (received in cycle 1, fee paid on it), less the washes."""
    if n == 0:
        repaid = ()
    elif grouped:
        repaid = (((amount, trust_in_unknown),),)
    else:
        repaid = tuple(((amount, trust_in_unknown),) for _ in range(n))
    due = largest_amount_due(repaid, **BELIEF)
    take = due / (1 + INTEREST) - max(FMIN, PHI * due) * (1 - KEEP)
    return take / (1 + R) - wash_cost(amount, n), due


def best_attack(trust_in_unknown, confederates=CONFEDERATES, grouped=False):
    options = [(*predicted_profit(m, n, trust_in_unknown, grouped), m, n)
               for n in confederates for m in (AMOUNTS if n else [0.0])]
    profit, due, amount, n = max(options)
    return dict(profit=profit, due=due, amount=amount, confederates=n)


def max_multiple(trust_in_unknown, n=1):
    """Prediction 3: the largest offer extractable, as a multiple of a stranger's."""
    u = (1 - trust_in_unknown) ** n
    return math.inf if u == 0 else 1 + (1 - P0) * (1 / u - 1)


# --- arms ---

def checked(amount, n, trust_in_unknown, grouped=False):
    """One attack by formula and by simulation."""
    trust = trusting({"bank": 1.0}, default=trust_in_unknown)
    group = (lambda who: "ring" if who.startswith("friend") else who) if grouped else None
    formula, due = predicted_profit(amount, n, trust_in_unknown, grouped)
    simulated, sim_due = simulate_attack(amount, n, trust, group)
    return dict(amount=amount, confederates=n, trust=trust_in_unknown, due=due, simulated_due=sim_due,
                profit=formula, simulated_profit=simulated, relative_error=abs(simulated - formula) / abs(formula))


def main():
    stranger = checked(0.0, 0, 0.0)
    base = stranger["profit"]

    a = []
    for m in (1e3, 1e4, 1e5):
        pv, _ = simulate_attack(m, 1, None, borrow=False)
        a.append(dict(amount=m, simulated_cost=-pv, formula_cost=wash_cost(m), share_of_amount=-pv / m))

    b = [checked(m, 1, 1.0) for m in (1e3, 1e4, 1e5)]
    for row in b:
        row["gain_over_stranger_per_unit"] = (row["simulated_profit"] - base) / row["amount"]

    c = []
    for t0 in (0.0, 0.5, 0.9, 0.99, 0.999):
        best = best_attack(t0, confederates=[0, 1])
        check = checked(best["amount"], best["confederates"], t0)
        c.append(dict(trust=t0, **best, multiple=best["due"] / STRANGER_DUE, predicted_multiple=max_multiple(t0),
                      gain_over_stranger=best["profit"] - base, simulated_profit=check["simulated_profit"],
                      relative_error=check["relative_error"]))

    d = []
    for t0 in (0.0, 0.1, 0.5, 0.9):
        best = best_attack(t0)
        check = checked(best["amount"], best["confederates"], t0)
        by_n = {str(n): best_attack(t0, confederates=[n])["due"] / STRANGER_DUE for n in CONFEDERATES}
        d.append(dict(trust=t0, **best, multiple=best["due"] / STRANGER_DUE, multiple_by_confederates=by_n,
                      simulated_profit=check["simulated_profit"], relative_error=check["relative_error"]))

    grouped = best_attack(0.5, grouped=True)
    check = checked(grouped["amount"], grouped["confederates"], 0.5, grouped=True)
    d_grouped = dict(trust=0.5, **grouped, multiple=grouped["due"] / STRANGER_DUE,
                     simulated_profit=check["simulated_profit"], relative_error=check["relative_error"])

    # E. an honest borrower whose record is with another real lender
    eco, _ = world()
    eco.add_agent("henry", money=2e7)
    eco.add_agent("other bank", money=2e7)
    eco.repay_loan(eco.loan("henry", "other bank", 1e4 / (1 + INTEREST), 1e4 - 1e4 / (1 + INTEREST)))
    full = offer(eco.log, "henry", None)
    e = []
    for t in (0.0, 0.5, 0.9, 0.99, 0.999, 1.0):
        due = offer(eco.log, "henry", trusting({"bank": 1.0, "other bank": t}))
        e.append(dict(trust=t, due=due, share_of_full=due / full, rungs_to_reclimb=math.log(full / due) / math.log(1.05)))

    # Control: climbing with the bank itself works whatever the bank thinks of strangers.
    control = {}
    for t0 in (0.0, 0.5):
        eco, _ = world()
        eco.add_agent("honest", money=2e7)
        offers = []
        for _ in range(6):
            due = offer(eco.log, "honest", trusting({"bank": 1.0}, default=t0))
            offers.append(due)
            eco.repay_loan(eco.loan("honest", "bank", due / (1 + INTEREST), due - due / (1 + INTEREST)))
        control[str(t0)] = dict(offers=offers, growth=[y / x for x, y in zip(offers, offers[1:])])

    worst = max([stranger["relative_error"]] + [r["relative_error"] for r in b + c + d + [d_grouped]])
    out = dict(provenance=run_provenance(),
               parameters=dict(kappa=KAPPA, delta=DELTA, r=R, fee_rate=PHI, min_fee=FMIN, interest=INTEREST, **BELIEF),
               stranger=stranger, A=a, B=b, C=c, D=d, D_grouped=d_grouped, E=e, control=control,
               worst_relative_error=worst)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Collusion: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"A stranger is offered {STRANGER_DUE:.1f} due; defaulting on it is worth {base:.1f} (present value).",
         f"Worst relative error, formula against simulation, over the attacks checked: {worst:.1e}.", "",
         "## A. What a wash costs", "", "| amount | cost (simulated) | cost (formula) | share of the amount |", "|---|---|---|---|"]
    L += [f"| {r['amount']:,.0f} | {r['simulated_cost']:.2f} | {r['formula_cost']:.2f} | {100 * r['share_of_amount']:.3f}% |" for r in a]
    L += ["", "## B. A bank that believes the whole log (one confederate)", "",
          "| washed | bank accepts (due) | attacker's profit | gain over a stranger, per unit washed |", "|---|---|---|---|"]
    L += [f"| {r['amount']:,.0f} | {r['simulated_due']:,.0f} | {r['simulated_profit']:,.0f} | {r['gain_over_stranger_per_unit']:.3f} |" for r in b]
    L += ["", "## C. One confederate, the attacker's best amount", "",
          "| bank's trust in unknown counterparties | best amount to wash | bank accepts, as a multiple of a stranger's | predicted multiple | gain over a stranger |",
          "|---|---|---|---|---|"]
    L += [f"| {r['trust']} | {r['amount']:,.0f} | {r['multiple']:.2f} | {r['predicted_multiple']:.2f} | {r['gain_over_stranger']:,.1f} |" for r in c]
    L += ["", "## D. Any number of confederates (up to 20), the attacker's best attack", "",
          "| trust in unknown | confederates | amount washed with each | bank accepts, multiple of a stranger's | profit | multiple at n = 1, 2, 5, 10, 20 |",
          "|---|---|---|---|---|---|"]
    for r in d:
        by_n = ", ".join(f"{r['multiple_by_confederates'][str(n)]:,.2f}" for n in CONFEDERATES[1:])
        L.append(f"| {r['trust']} | {r['confederates']} | {r['amount']:,.0f} | {r['multiple']:,.2f} | {r['profit']:,.0f} | {by_n} |")
    r = d_grouped
    L += ["", f"With trust 0.5 and the confederates known to be one group: best attack uses {r['confederates']} confederate(s), "
          f"washes {r['amount']:,.0f}, and the bank accepts {r['multiple']:.2f} times a stranger's (profit {r['profit']:,.1f}).",
          "", "## E. An honest borrower who repaid 10,000 to another real lender", "",
          "| bank's trust in that lender | bank accepts (due) | share of what full trust gives | rungs of a 5% ladder still to climb |", "|---|---|---|---|"]
    L += [f"| {r['trust']} | {r['due']:,.1f} | {100 * r['share_of_full']:.1f}% | {r['rungs_to_reclimb']:.0f} |" for r in e]
    L += ["", "## Control: an honest borrower climbing with the bank itself", ""]
    L += [f"- trust in unknown {t0}: offers {', '.join(f'{x:.1f}' for x in v['offers'])} (growth {v['growth'][0]:.4f} each)" for t0, v in control.items()]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
