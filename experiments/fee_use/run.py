"""
Claim under test: no use of the fee revenue makes a faked record dearer than an honest one; rules that
return the fee to the pair make faking cheap, and rules that pay on claims or per identity are drained.
See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from rain import economics
from rain.model import Economy
from rain.provenance import run_provenance
from rain.record import largest_amount_due

HERE = Path(__file__).parent
KAPPA, DELTA, R, PHI, FMIN, INTEREST = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05
RHO, FLOOR, TAIL, SHOCK = 0.10, 100.0, 1.0, 0.02
BELIEF = dict(risk_tolerance=RHO, floor=FLOOR, tail_index=TAIL, shock_rate=SHOCK)
P0 = (1 - RHO) / (1 - SHOCK)
KEEP = DELTA / (R + DELTA)  # share of a fee that the reputation dividend returns, in present value
STRANGER_DUE = largest_amount_due((), **BELIEF)
VOLUME, DEFAULTED = 1e6, 0.02  # honest promises per cycle, and the share of them broken
COVER, WORK_SHARE = 0.5, 0.5
HORIZON = 600


# --- what comes back, rule by rule: (to a ring washing with itself, to an honest promisor) as shares of the fee ---

def returned(n_honest=10_000):
    work_self = WORK_SHARE + (1 - WORK_SHARE) * KEEP
    work_other = (1 - WORK_SHARE) * KEEP
    return {
        "1. dividend (current)": (KEEP, KEEP),
        "2. burn": (0.0, 0.0),
        "3. counterparty": (1.0, 0.0),
        "4. insurance": (0.0, 0.0),
        "5. work, presented by the payer": (work_self, work_self),
        "5. work, presented by someone else": (work_other, work_other),
        "6. per identity": (2 / (n_honest + 2), 1 / (n_honest + 1)),
        "7. forfeitable dividend": (KEEP, KEEP),
    }


# --- rule 1 through the model of the contracts ---

def world(fee_flow=1e7):
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=fee_flow / KAPPA / DELTA)
    eco.start_in_steady_state(fee_flow)

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=fee_flow / PHI)
    return eco, tick


def simulated_wash_cost(amount=1e4):
    """Present value lost by a pair who pass `amount` between them once, under the current rules, per unit."""
    eco, tick = world()
    for name in ("a", "b"):
        eco.add_agent(name, money=2e6)
    money = lambda: math.fsum(eco.agents[n].money for n in ("a", "b"))
    start = money()
    eco.repay_loan(eco.loan("a", "b", amount, 0.0))
    pv = money() - start
    for t in range(1, HORIZON + 1):
        before = money()
        tick()
        pv += (money() - before) / (1 + R) ** t
    return -pv / amount


def simulated_ladder_standing(rungs=80):
    """
    The value of the reputation held by a borrower who has repaid `rungs` loans, each 1.089 times the
    last, one a cycle, when the next falls due: as a share of that amount. This is what rule 7 would
    take from them if they defaulted on it.
    """
    growth = (1 - SHOCK) / (1 - RHO)
    eco, tick = world()
    eco.add_agent("bank", money=1e30)
    eco.add_agent("borrower", money=1e30)
    due = 100.0
    loan = eco.loan("borrower", "bank", due / (1 + INTEREST), due - due / (1 + INTEREST))
    for _ in range(rungs):
        tick()
        eco.repay_loan(loan)
        due *= growth
        loan = eco.loan("borrower", "bank", due / (1 + INTEREST), due - due / (1 + INTEREST))
    tick()  # the last loan falls due
    value = eco.agents["borrower"].reputation * economics.current_point_value(KAPPA, R, DELTA)
    return value / due


def predicted_ladder_standing(count_current_loan=False):
    growth = (1 - SHOCK) / (1 - RHO)
    x = (1 - DELTA) / growth
    series = 1 / (1 - x) if count_current_loan else x / (1 - x)
    return PHI * KEEP * series


# --- safe trust in unknown counterparties, given what a wash costs (the method of collusion/, part G) ---

def ring_gain(trust_in_unknown, returned_share, max_confederates=3000):
    def take(due):
        return (due / (1 + INTEREST) - np.maximum(FMIN, PHI * due)) / (1 + R)

    n = np.arange(1, max_confederates + 1)[:, None]
    amount = np.logspace(2, 8, 601)[None, :]
    u = (1 - trust_in_unknown) ** n
    s = np.minimum(1.0, (FLOOR / amount) ** TAIL)
    above = P0 * (u * (1 - s) + s)
    below = P0 + s * (1 - P0) * (1 - 1 / np.maximum(u, 1e-300))
    survival = np.where(above <= s, above, below)
    due = FLOOR / np.clip(survival, 1e-300, 1.0) ** (1 / TAIL)
    gain = take(due) - n * np.maximum(FMIN, PHI * amount) * (1 - returned_share) - take(np.array(STRANGER_DUE))
    return float(gain.max())


def safe_trust(returned_share):
    lo, hi = 0.0, 0.5
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ring_gain(mid, returned_share) <= 1e-9 else (lo, mid)
    return lo


# --- rules that pay on something a ring can make: claims, identities ---

def insurance(fake_ratio):
    """A cycle of rule 4 with a ring whose fake defaults are `fake_ratio` times the honest ones."""
    honest_losses = VOLUME * DEFAULTED
    fake = fake_ratio * honest_losses
    pool = PHI * (VOLUME + fake)
    claims = COVER * (honest_losses + fake)
    paid = min(1.0, pool / claims)
    ring_receives = COVER * fake * paid
    return dict(fake_ratio=fake_ratio, pool=pool, share_of_claims_paid=paid, ring_fee=PHI * fake, ring_receives=ring_receives,
                ring_profit=ring_receives - PHI * fake, ring_share_of_pool=ring_receives / pool,
                honest_recover_share_of_loss=COVER * paid)


def per_identity(k_over_n):
    return dict(identities_per_honest_identity=k_over_n, ring_share_of_revenue=k_over_n / (1 + k_over_n))


def main():
    rules = {}
    for name, (to_ring, to_honest) in returned().items():
        rules[name] = dict(wash_cost=PHI * (1 - to_ring), honest_cost=PHI * (1 - to_honest), safe_trust=safe_trust(to_ring))
    control = simulated_wash_cost()
    standing = dict(simulated=simulated_ladder_standing(), predicted=predicted_ladder_standing(),
                    as_first_predicted=predicted_ladder_standing(count_current_loan=True))
    out = dict(provenance=run_provenance(),
               parameters=dict(fee_rate=PHI, r=R, decay=DELTA, dividend_share=KEEP, cover=COVER, work_share=WORK_SHARE,
                               honest_volume=VOLUME, honest_default_share=DEFAULTED),
               rules=rules, control_wash_cost_simulated=control,
               insurance=[insurance(x) for x in (0.0, 1.0, 10.0, 100.0)],
               insurance_break_even_share_paid=PHI / COVER,
               per_identity=[per_identity(x) for x in (0.1, 1.0, 10.0)],
               forfeit_as_share_of_amount_due=standing)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# What should the fees pay for? Results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         "| rule | net cost of washing one unit | net cost of an honest promise of one unit | safe trust in unknown counterparties |", "|---|---|---|---|"]
    L += [f"| {name} | {100 * r['wash_cost']:.4f}% | {100 * r['honest_cost']:.4f}% | {100 * r['safe_trust']:.2f}% |" for name, r in rules.items()]
    L += ["", f"Control: under the current rules a wash costs {100 * control:.4f}% in the model of the contracts.", "",
          "## Rule 4: insurance, with a ring that fakes defaults", "",
          "| fake defaults, as a multiple of honest ones | share of each claim paid | ring's fee | ring receives | ring's share of the pool | honest promisees recover, of their loss |",
          "|---|---|---|---|---|---|"]
    L += [f"| {r['fake_ratio']:.0f} | {100 * r['share_of_claims_paid']:.1f}% | {r['ring_fee']:,.0f} | {r['ring_receives']:,.0f} | "
          f"{100 * r['ring_share_of_pool']:.1f}% | {100 * r['honest_recover_share_of_loss']:.1f}% |" for r in out["insurance"]]
    L += ["", f"The ring profits while claims are paid at more than {100 * PHI / COVER:.0f}% of the cover promised.", "",
          "## Rule 6: per identity", "", "| ring's identities per honest identity | ring's share of all revenue |", "|---|---|"]
    L += [f"| {r['identities_per_honest_identity']} | {100 * r['ring_share_of_revenue']:.1f}% |" for r in out["per_identity"]]
    L += ["", "## Rule 7: what a defaulter on a ladder would forfeit", "",
          f"Reputation worth {100 * standing['simulated']:.2f}% of the amount due (model), {100 * standing['predicted']:.2f}% (formula). "
          f"The prediction in the README counted the fee on the loan being defaulted on: {100 * standing['as_first_predicted']:.2f}%."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
