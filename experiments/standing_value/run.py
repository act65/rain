"""
Claim under test: `rain.ladder.ladder_default_account` gives what a borrower on a ladder gains and
loses by defaulting, and most of the loss is access to future credit, not dividends. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from rain import ladder
from rain.model import Economy
from rain.provenance import run_provenance

HERE = Path(__file__).parent
KAPPA, DELTA, R, PHI, FMIN, INTEREST = 0.04, 0.03, 0.05, 0.01, 0.1, 0.05
FIRST, GROWTH, CAP = 100.0, 1.05, 5000.0
LADDER = dict(first_loan=FIRST, growth=GROWTH, cap=CAP, interest_rate=INTEREST, r=R,
              fee_rate=PHI, min_fee=FMIN, point_price=KAPPA, decay_rate=DELTA)
SURPLUSES = [0.01, 0.03, 0.06]
RUNGS = list(range(0, 121))
CHECK = [0, 10, 40, 81, 110]
HORIZON = 500


def loan_size(n):
    return min(FIRST * GROWTH**n, CAP)


def discounted_money(rung, sigma, default, restart, fee_flow=1e7):
    """Borrower's discounted money from the cycle of loan `rung` on, in a large steady economy."""
    eco = Economy.current_rules(min_fee=FMIN, fee_rate=PHI, point_price=KAPPA, decay_rate=DELTA)
    eco.add_agent("world", money=1e30, reputation=fee_flow / KAPPA / DELTA)
    eco.add_agent("lender", money=1e30)
    first = eco.add_agent("first identity", money=1e15)
    second = eco.add_agent("second identity", money=1e15)
    eco.start_in_steady_state(fee_flow)

    def tick():
        eco.pay_dividend()
        eco.kept_promises("world", amount=fee_flow / PHI)

    def take(name, n):
        agent = eco.agents[name]
        loan = eco.loan(name, "lender", loan_size(n), INTEREST * loan_size(n), bond=agent.liquid_reputation)
        agent.money += (sigma + INTEREST) * loan_size(n)  # what the borrowed money earned
        return loan

    def money():
        return first.money + second.money

    for n in range(rung):  # the climb so far, the same in both branches
        tick()
        eco.repay_loan(take("first identity", n))
    tick()
    loan = take("first identity", rung)
    before = money()
    if default:
        eco.default_loan(loan)
    else:
        eco.repay_loan(loan)
    pv = money() - before
    for j in range(1, HORIZON):
        before = money()
        tick()
        if not default:
            eco.repay_loan(take("first identity", rung + j))
        elif restart:
            eco.repay_loan(take("second identity", j - 1))
        pv += (money() - before) / (1 + R) ** j
    return pv


def main():
    accounts, checks = {}, []
    for sigma in SURPLUSES:
        for restart in (False, True):
            key = f"sigma={sigma}, {'can start again' if restart else 'shut out for good'}"
            rows = [ladder.ladder_default_account(n, surplus_rate=sigma, restart=restart, **LADDER) for n in RUNGS]
            unsafe = [n for n, a in zip(RUNGS, rows) if a["gain"] > 0]
            safe = [n for n in RUNGS if n not in unsafe]
            at = {str(n): rows[n] for n in (0, 10, 20, 40, 60, 81, 120)}
            accounts[key] = dict(
                first_safe_rung=min(safe) if safe else None, last_safe_rung=max(safe) if safe else None,
                safe_rungs=len(safe), default_pays_at_cap=rows[120]["gain"] > 0, at=at,
                dividend_share_at={str(n): rows[n]["dividends"] / (rows[n]["dividends"] + rows[n]["access"])
                                   for n in (10, 40, 81, 120) if rows[n]["access"] > 0},
            )
            if sigma == 0.03:
                for n in CHECK:
                    simulated = discounted_money(n, sigma, True, restart) - discounted_money(n, sigma, False, restart)
                    checks.append(dict(case=key, rung=n, account=rows[n]["gain"], simulated=simulated,
                                       error_over_kept=abs(simulated - rows[n]["gain"]) / rows[n]["kept"]))

    out = dict(provenance=run_provenance(), ladder=LADDER, accounts=accounts, checks=checks)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    L = ["# What a default really costs: results", "",
         f"Commit `{out['provenance']['commit_short']}` (dirty: {out['provenance']['dirty']}), {out['provenance']['utc']}.", "",
         f"Account against simulation (3% surplus): worst error {max(c['error_over_kept'] for c in checks):.1e} of the amount kept, over {len(checks)} checks.", "",
         "## Where default pays", "",
         "| case | rungs where default does NOT pay (of 0 to 120) | pays at the cap? |", "|---|---|---|"]
    for key, a in accounts.items():
        span = "none" if not a["safe_rungs"] else f"{a['first_safe_rung']} to {a['last_safe_rung']} ({a['safe_rungs']} rungs)"
        L.append(f"| {key} | {span} | {'yes' if a['default_pays_at_cap'] else 'no'} |")
    L += ["", "## The account at selected rungs (DMD)", "",
          "| case | rung | loan | kept by defaulting | reputation held | dividends lost | access lost | gain from default | dividends as share of the loss |",
          "|---|---|---|---|---|---|---|---|---|"]
    for key, a in accounts.items():
        for n, row in a["at"].items():
            loss = row["dividends"] + row["access"]
            share = f"{row['dividends'] / loss:.0%}" if row["access"] > 0 else "n/a"
            L.append(f"| {key} | {n} | {row['loan']:.0f} | {row['kept']:.0f} | {row['reputation']:.0f} | {row['dividends']:.1f} | {row['access']:.1f} | {row['gain']:+.1f} | {share} |")
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:14]))
    print("\n".join(l for l in L[14:] if "| 0 |" in l or "| 40 |" in l or "| 120 |" in l or l.startswith("| case") or l.startswith("|---")))


if __name__ == "__main__":
    main()
