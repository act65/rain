"""
Claim under test: what a lender should risk on a stranger follows from the value of the relationship
it may start (the first loan's expected loss is the price of information); with thresholds of tail
index 1 the lender never raises a loan; and with opportunists who can return, the first loan is
bounded by the cost of an identity. See README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rain import ladder
from rain.provenance import run_provenance

HERE = Path(__file__).parent
FLOOR, TOP, I, Q, R, PHI = 100.0, 1e4, 0.05, 0.02, 0.05, 0.01
BETA = 1 / (1 + R)
SHARES = [0.0, 0.1, 0.2, 0.3, 0.31, 0.4]


# --- the dynamic programme: every sequence of loan sizes ---

def solve(tail, interest=I, top=TOP, points=401, growth_cap=None, bottom=FLOOR):
    """
    The lender's best policy for a borrower whose largest repayment is M (on a log grid from the
    floor to `top`). Returns (grid, value, index of the best next amount due; -1 means stop lending).
    """
    grid = np.geomspace(bottom, top, points)
    principal = grid / (1 + interest)
    idx = np.arange(points)
    known = np.maximum(grid, FLOOR)  # everyone genuine is good for the floor, whatever they have repaid so far
    repay = (1 - Q) * np.minimum(1.0, (known[:, None] / grid[None, :]) ** tail)
    nxt = np.maximum(idx[:, None], idx[None, :])
    allowed = np.ones((points, points), dtype=bool)
    if growth_cap is not None:
        allowed = grid[None, :] <= grid[:, None] * growth_cap * (1 + 1e-9)
    value = np.zeros(points)
    for _ in range(20000):
        q_value = repay * (interest * principal[None, :] + BETA * value[nxt]) - (1 - repay) * principal[None, :]
        q_value[~allowed] = -np.inf
        best = q_value.max(axis=1)
        new = np.maximum(best, 0.0)
        if np.max(np.abs(new - value)) < 1e-10 * max(1.0, np.max(np.abs(new))):
            value = new
            break
        value = new
    policy = np.where(best > 0, q_value.argmax(axis=1), -1)
    return grid, value, policy


def best_first_loan(opportunist_share, grid, value, tail=1.0, interest=I):
    """The best first amount due to a stranger (0 if none is worth making), searching below the floor as well."""
    first = np.concatenate([np.geomspace(FLOOR / 20, FLOOR, 60, endpoint=False), grid])
    principal = first / (1 + interest)
    repay = (1 - Q) * np.minimum(1.0, (FLOOR / first) ** tail)
    after = np.interp(np.maximum(first, FLOOR), grid, value)  # a survivor is known to be good for the floor at least
    genuine = repay * (interest * principal + BETA * after) - (1 - repay) * principal
    total = -opportunist_share * principal + (1 - opportunist_share) * genuine
    j = int(np.argmax(total))
    return (float(first[j]), float(total[j])) if total[j] > 0 else (0.0, 0.0)


def capped_first_loan(opportunist_share, grid, value, policy, interest=I):
    """
    The best first amount due when every later loan is at most `1 + interest` times the largest
    repaid. A stranger who repays X is in state X of the capped programme. Returns (due, value).
    """
    principal = grid / (1 + interest)
    repay = (1 - Q) * np.minimum(1.0, FLOOR / grid)
    genuine = repay * (interest * principal + BETA * value) - (1 - repay) * principal
    total = -opportunist_share * principal + (1 - opportunist_share) * genuine
    j = int(np.argmax(total))
    return (float(grid[j]), float(total[j]), j) if total[j] > 0 else (0.0, 0.0, -1)


def follow(grid, policy, start, horizon):
    """The amounts due along the capped policy for a borrower who keeps repaying, from first loan `start`."""
    dues, j = [float(grid[start])], start
    for _ in range(horizon - 1):
        j = int(policy[j])
        dues.append(float(grid[j]))
    return dues


# --- Monte Carlo: borrowers, one by one ---

def simulate(dues, opportunist_share, n=400_000, seed=0, tail=1.0, interest=I):
    """Mean discounted profit per stranger (and its standard error) of offering `dues[t]` as the t-th loan."""
    rng = np.random.default_rng(seed)
    opportunist = rng.random(n) < opportunist_share
    threshold = FLOOR * (1 - rng.random(n)) ** (-1 / tail)
    profit = np.where(opportunist, -dues[0] / (1 + interest), 0.0)
    alive = ~opportunist
    for t, due in enumerate(dues):
        if due <= 0 or not alive.any():
            break
        repaid = alive & (threshold >= due) & (rng.random(n) >= Q)
        principal = due / (1 + interest)
        profit += BETA**t * np.where(repaid, interest * principal, np.where(alive, -principal, 0.0))
        alive = repaid
    return float(profit.mean()), float(profit.std() / np.sqrt(n))


def main():
    v = ladder.repeat_value(I, Q, R)
    lo, hi = ladder.opportunist_share_bounds(I, Q, R)

    # 1. the best policy for a known borrower, tail index 1
    grid, value, policy = solve(1.0)
    raises = int(np.sum(policy > np.arange(len(grid))))
    p1 = dict(grid_points=len(grid), states_where_the_loan_is_raised=raises,
              value_per_unit_due=float(value[0] / FLOOR), repeat_value=v,
              worst_gap_to_repeating=float(np.max(np.abs(value / grid - v))))

    # 2, 3. the first loan, by opportunist share
    p2 = []
    for share in SHARES:
        due, total = best_first_loan(share, grid, value)
        formula = ladder.stranger_value(FLOOR, share, FLOOR, 1.0, I, Q, R)
        p2.append(dict(share=share, best_first_due=due, value=total, formula_value=max(0.0, formula["relationship"]),
                       first_loan_alone=formula["first_loan"], price_of_information=formula["price_of_information"]))

    # 4. simulation of "lend the floor, and again while it is repaid"
    horizon = 600
    repeat = [FLOOR] * horizon
    p4 = []
    for share in (0.0, 0.1, 0.2, 0.3, 0.4):
        mean, se = simulate(repeat, share)
        formula = ladder.stranger_value(FLOOR, share, FLOOR, 1.0, I, Q, R)["relationship"]
        p4.append(dict(share=share, simulated=mean, standard_error=se, formula=formula))

    # 5. other policies, at a 10% share
    k10 = ladder.screening_growth_factor(0.10, 1.0, Q)
    policies = {
        "repeat the floor": repeat,
        "accept 10% risk on every loan (each 1.089 times the last)": [min(FLOOR * k10 ** (t + 1), TOP) for t in range(horizon)],
        "double every loan": [min(FLOOR * 2.0**t, TOP) for t in range(horizon)],
        "raise by the interest rate (1.05)": [min(FLOOR * 1.05**t, TOP) for t in range(horizon)],
    }
    p5 = {}
    for name, dues in policies.items():
        mean, se = simulate(dues, 0.10, seed=1)
        p5[name] = dict(simulated=mean, standard_error=se)
    one_shot = ladder.stranger_value(FLOOR, 0.10, FLOOR, 1.0, I, Q, R)["first_loan"]
    p5["require every loan to break even (myopic)"] = dict(simulated=0.0, standard_error=0.0, note=f"the first loan alone expects {one_shot:.2f}, so it is refused")

    # 6. when does raising the loan pay? (far below what the borrower can use)
    p6 = []
    for interest in (0.05, 0.10, 0.20):
        tails = np.round(np.arange(0.10, 1.001, 0.02), 2)
        grows = []
        for tail in tails:
            g, _, pol = solve(float(tail), interest=interest, top=FLOOR * 1e6, points=601)
            grows.append(bool(pol[0] > 0))
        largest = max((float(t) for t, yes in zip(tails, grows) if yes), default=None)
        predicted = max((float(t) for t in tails if ladder.growth_pays(float(t), interest, Q, R)), default=None)
        g, _, pol = solve(0.2, interest=interest, top=FLOOR * 1e6, points=601)
        p6.append(dict(interest=interest, largest_tail_index_with_growth=largest, predicted=predicted,
                       step_at_tail_0_2=float(g[pol[0]] / g[0])))

    # 7. opportunists who can come back: the lender's best first amount due
    candidates = np.round(np.arange(1.0, 150.01, 0.1), 1)
    p7 = []
    for m in (0.25, 1.0, 10.0):
        for cost in (0.0, 20.0, 60.0, 120.0):
            bound = ladder.identity_bound(cost, PHI, I)
            values = []
            for due in candidates:
                genuine = ladder.stranger_value(float(due), 0.0, FLOOR, 1.0, I, Q, R)["relationship"]
                flood = m * due / (1 + I) if due / (1 + I) - PHI * due > cost + 1e-12 else 0.0
                values.append(genuine - flood)
            j = int(np.argmax(values))
            p7.append(dict(applications_per_genuine=m, identity_cost=cost, identity_bound=bound,
                           best_first_due=float(candidates[j]) if values[j] > 1e-9 else 0.0, value=max(0.0, float(values[j]))))

    # Follow-up (8 to 10): each loan at most 1 + i times the largest repaid, from the first loan on.
    cgrid, cvalue, cpolicy = solve(1.0, growth_cap=1 + I, bottom=FLOOR / 100, points=945)  # grid ratio 1.05 ** (1 / 5)
    step = np.where(cpolicy >= 0, cgrid[np.maximum(cpolicy, 0)] / cgrid, 0.0)
    below, above = cgrid < FLOOR / 1.05, cgrid >= FLOOR
    p8 = dict(step_below_floor=[float(step[below].min()), float(step[below].max())],
              step_at_or_above_floor=[float(step[above].min()), float(step[above].max())], rows=[])
    for share in (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.58, 0.6, 0.65):
        due, total, j = capped_first_loan(share, cgrid, cvalue, cpolicy)
        repeat_only = max(0.0, ladder.stranger_value(FLOOR, share, FLOOR, 1.0, I, Q, R)["relationship"])
        row = dict(share=share, best_first_due=due, value=total, value_of_lending_the_floor=repeat_only)
        if j >= 0:
            principal = due / (1 + I)
            row["first_loan_alone"] = -share * principal + (1 - share) * ((1 - Q) * I * principal - Q * principal)
        p8["rows"].append(row)
    lending = [r["share"] for r in p8["rows"] if r["value"] > 0]
    p8["largest_share_with_lending"] = max(lending)

    p9 = []
    for cost in (20.0, 60.0):
        bound = ladder.identity_bound(cost, PHI, I)
        j = int(np.searchsorted(cgrid, bound, side="right") - 1)  # the largest grid amount within the bound
        p9.append(dict(identity_cost=cost, identity_bound=bound, start=float(cgrid[j]),
                       value_climbing=float(cvalue[j]) if False else float(
                           (1 - Q) * (I * cgrid[j] / (1 + I) + BETA * cvalue[j]) - Q * cgrid[j] / (1 + I)),
                       value_repeating=ladder.stranger_value(float(cgrid[j]), 0.0, FLOOR, 1.0, I, Q, R)["relationship"]))

    due, total, j = capped_first_loan(0.3, cgrid, cvalue, cpolicy)
    mean, se = simulate(follow(cgrid, cpolicy, j, horizon), 0.3, seed=2)
    p10 = dict(share=0.3, first_due=due, programme=total, simulated=mean, standard_error=se)

    out = dict(provenance=run_provenance(), follow_up=dict(capped_first_loan=p8, identity_then_climb=p9, simulation=p10), parameters=dict(floor=FLOOR, top=TOP, interest=I, shock=Q, r=R, fee_rate=PHI),
               repeat_value=v, share_bounds=dict(first_loan_loses_above=lo, no_lending_above=hi),
               known_borrower=p1, first_loan=p2, simulation=p4, policies=p5, growth=p6, identity=p7)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# The first loan: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"A borrower known to repay an amount is worth {v:.3f} per unit of it to the lender.",
         f"A first loan loses money in expectation above {100 * lo:.1f}% opportunists; no lending to strangers above {100 * hi:.1f}%.", "",
         "## 1. A known borrower, tail index 1", "",
         f"Of {p1['grid_points']} states, the best policy raises the loan in {p1['states_where_the_loan_is_raised']}. "
         f"Value per unit due {p1['value_per_unit_due']:.4f} (repeating: {v:.4f}).", "",
         "## 2, 3. The first loan", "",
         "| opportunist share | best first amount due | relationship value | formula | first loan alone | price of information |", "|---|---|---|---|---|---|"]
    L += [f"| {100 * r['share']:.0f}% | {r['best_first_due']:.1f} | {r['value']:.2f} | {r['formula_value']:.2f} | {r['first_loan_alone']:+.2f} | {r['price_of_information']:.2f} |" for r in p2]
    L += ["", "## 4. Simulation of lending the floor repeatedly (400,000 strangers)", "",
          "| opportunist share | simulated value | standard error | formula |", "|---|---|---|---|"]
    L += [f"| {100 * r['share']:.0f}% | {r['simulated']:.2f} | {r['standard_error']:.2f} | {r['formula']:.2f} |" for r in p4]
    L += ["", "## 5. Policies compared, 10% opportunists (value per stranger)", "", "| policy | value | standard error |", "|---|---|---|"]
    L += [f"| {name} | {r['simulated']:.1f} | {r['standard_error']:.1f} |" for name, r in p5.items()]
    L += ["", "## 6. When raising the loan pays", "",
          "| interest | largest tail index at which the best policy raises the loan | predicted | step at tail index 0.2 |", "|---|---|---|---|"]
    L += [f"| {100 * r['interest']:.0f}% | {r['largest_tail_index_with_growth']} | {r['predicted']} | {r['step_at_tail_0_2']:.2f} |" for r in p6]
    L += ["", "## 7. Opportunists who can come back: the best first amount due", "",
          "| opportunist applications per genuine borrower | identity cost | identity bound | best first amount due | value per genuine borrower |", "|---|---|---|---|---|"]
    L += [f"| {r['applications_per_genuine']} | {r['identity_cost']:.0f} | {r['identity_bound']:.1f} | {r['best_first_due']:.1f} | {r['value']:.1f} |" for r in p7]
    L += ["", "## Follow-up: each loan at most 1.05 times the largest repaid", "",
          f"Best step below the floor: {p8['step_below_floor'][0]:.3f} to {p8['step_below_floor'][1]:.3f}; "
          f"at or above the floor: {p8['step_at_or_above_floor'][0]:.3f} to {p8['step_at_or_above_floor'][1]:.3f}. "
          f"Largest share tried at which strangers are still lent to: {100 * p8['largest_share_with_lending']:.0f}%.", "",
          "| opportunist share | best first amount due | relationship value | value of starting at the floor | first loan alone |", "|---|---|---|---|---|"]
    L += [f"| {100 * r['share']:.0f}% | {r['best_first_due']:.1f} | {r['value']:.2f} | {r['value_of_lending_the_floor']:.2f} | "
          + (f"{r['first_loan_alone']:+.2f}" if "first_loan_alone" in r else "-") + " |" for r in p8["rows"]]
    L += ["", "Returning opportunists, unlimited: start at the identity bound and climb.", "",
          "| identity cost | start | value climbing to the floor | value repeating the start |", "|---|---|---|---|"]
    L += [f"| {r['identity_cost']:.0f} | {r['start']:.1f} | {r['value_climbing']:.1f} | {r['value_repeating']:.1f} |" for r in p9]
    L += ["", f"Simulation of the best policy at a 30% share (first loan {p10['first_due']:.1f}): "
          f"{p10['simulated']:.2f} (standard error {p10['standard_error']:.2f}); programme {p10['programme']:.2f}."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
