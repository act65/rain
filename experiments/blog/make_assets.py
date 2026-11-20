"""
Generates what the blog posts about Rain need from the experiments: the charts (SVG) and a YAML
file of every number the posts quote, so that no number is typed by hand.

    python experiments/blog/make_assets.py <output directory>

Numbers are read from the experiments' `results/results.json`. The time series for the charts are
re-simulated here with the same library calls (the result files keep only summary points).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rain import ladder
from rain.model import Economy
from rain.provenance import run_provenance

ROOT = Path(__file__).resolve().parents[1]
# Categorical slots 1 to 4 of the reference palette, in fixed order; ink and surface tokens.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
KAPPA, DELTA, R = 0.04, 0.03, 0.05

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "lines.linewidth": 2, "legend.frameon": False, "svg.fonttype": "none",
})


def results(name):
    return json.loads((ROOT / name / "results" / "results.json").read_text())


def figure(height=4.0):
    fig, ax = plt.subplots(figsize=(7.2, height))
    return fig, ax


def end_label(ax, x, y, text, dy=0.0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points", color=INK, va="center", fontsize=10)


def save(fig, out, name):
    fig.tight_layout()
    fig.savefig(out / name, format="svg")
    if os.environ.get("RAIN_PREVIEW"):  # bitmaps for checking the layout by eye
        fig.savefig(out / name.replace(".svg", ".png"), format="png", dpi=110)
    plt.close(fig)


# --- chart 1: the fee under the original keeper ---

def keeper_fee(out):
    eco = Economy(fee=0.1, yield_rate=0.004)
    eco.add_agent("honest", money=1e30, reputation=10_000.0)
    fees = []
    for _ in range(300):
        fees.append(eco.fee)
        eco.kept_promises("honest", 100)
        eco.pay_dividend()
        eco.update_fee(margin=1.5, r=R)
    fig, ax = figure()
    ax.plot(range(300), fees, color=BLUE)
    ax.set_yscale("log")
    ax.set_xlabel("dividend cycle")
    ax.set_ylabel("fee per promise (DMD, log scale)")
    ax.set_title("The original fee keeper: the fee has nothing to hold it up", loc="left", color=INK, fontsize=12)
    end_label(ax, 0, fees[0], "starts at 0.1", dy=2)
    end_label(ax, 299, fees[-1], f"{fees[-1]:.5f}")
    ax.set_xlim(0, 345)
    save(fig, out, "keeper-fee.svg")
    return dict(first=fees[0], after_first_update=fees[1], at_300=fees[-1])


# --- chart 2: value of a point / its cost, three ways of paying fees out ---

def value_over_cost(eco, surge_at=300, horizon=1500, base=100):
    eco.add_agent("honest", money=1e30)
    d = []
    for t in range(horizon):
        eco.kept_promises("honest", base * (10 if t >= surge_at else 1))
        eco.run_oracle()
        earning = sum(a.earning_reputation for a in eco.agents.values())
        d.append(eco.pay_dividend() / earning)
    values, tail = [0.0] * horizon, d[-1] / (R + DELTA)
    for t in range(horizon - 1, -1, -1):
        tail = (d[t] + (1 - DELTA) * tail) / (1 + R)
        values[t] = tail / KAPPA
    return values


def payout_designs(out):
    rules = dict(min_fee=1.0, fee_rate=0.0, point_price=KAPPA, decay_rate=DELTA)
    designs = [
        ("paid out as received", ORANGE, Economy(fee=1.0, point_price=KAPPA, decay_rate=DELTA, pass_through=True)),
        ("starting allocation + reserve", AQUA, Economy.genesis_rules(reserve_release=0.03, genesis_reputation=100 / KAPPA / DELTA, **rules)),
        ("payout fund (adopted)", BLUE, Economy.current_rules(**rules)),
    ]
    fig, ax = figure()
    peaks = {}
    for label, colour, eco in designs:
        v = value_over_cost(eco)[:500]
        ax.plot(range(500), v, color=colour, label=label)
        peaks[label] = dict(start=v[0], start_peak=max(v[:100]), surge_peak=max(v[300:400]))
    ax.axhline(1.0, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(60, 1.05, "above this line, buying reputation pays", color=MUTED, fontsize=9)
    ax.axvline(300, color=GRID, linewidth=1)
    ax.text(304, 0.06, "activity rises tenfold", color=MUTED, fontsize=9)
    ax.set_ylim(0, 3.0)
    ax.set_xlim(0, 500)
    ax.set_xlabel("dividend cycle in which the point was earned")
    ax.set_ylabel("value of a point / what it cost")
    ax.set_title("Three ways to pay fees out, from an empty start through a surge", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, -0.18))
    save(fig, out, "payout-designs.svg")
    return peaks


# --- chart 3: what a default gains, by rung of the ladder ---

def default_by_rung(out):
    spec = dict(first_loan=100.0, growth=1.05, cap=5000.0, interest_rate=0.05, r=R,
                fee_rate=0.01, min_fee=0.1, point_price=KAPPA, decay_rate=DELTA)
    cases = [
        ("gains 3% a loan, shut out for good", BLUE, 0.03, False),
        ("gains 3% a loan, can start again", ORANGE, 0.03, True),
        ("gains 6% a loan, can start again", AQUA, 0.06, True),
    ]
    rungs = list(range(0, 121))
    fig, ax = figure(4.8)
    for label, colour, sigma, restart in cases:
        accounts = [ladder.ladder_default_account(n, surplus_rate=sigma, restart=restart, **spec) for n in rungs]
        ax.plot(rungs, [a["gain"] / a["kept"] for a in accounts], color=colour, label=label)
    ax.axhline(0.0, color=MUTED, linewidth=1)
    ax.text(1, 0.04, "default pays above the line", color=MUTED, fontsize=9)
    ax.axvline(81, color=GRID, linewidth=1)
    ax.text(83, -1.35, "loan size reaches its cap", color=MUTED, fontsize=9)
    ax.set_xlim(0, 120)
    ax.set_xlabel("loan number on the ladder (each 5% larger than the last, up to a cap)")
    ax.set_ylabel("gain from default / amount kept")
    ax.set_title("Default pays at the bottom of a ladder and where it stops growing", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper center", ncol=1, fontsize=9, bbox_to_anchor=(0.5, -0.18))
    save(fig, out, "default-by-rung.svg")


# --- chart 4: how fast to forget ---

def forgetting(out):
    data = results("bayes_decay")
    gammas = [0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 1.0]
    fig, ax = figure(4.8)
    for hazard, colour in (("0.005", BLUE), ("0.02", ORANGE), ("0.05", AQUA)):
        summary = data["results"][hazard]["summary"]
        exact = summary["exact"]["mean"]
        excess = [summary[f"gamma={g}"]["mean"] - exact for g in gammas]
        forget = [1 - g for g in gammas]
        ax.plot(forget, excess, color=colour, marker="o", markersize=4, label=f"people change with probability {hazard} per promise")
        ax.margins(x=0.03)
        best = min(range(len(gammas)), key=lambda i: excess[i])
        ax.plot([forget[best]], [excess[best]], marker="o", markersize=9, markerfacecolor="none", markeredgecolor=INK, linestyle="none")
        ax.axvline(float(hazard), color=colour, linewidth=1, linestyle=(0, (2, 3)))
    ax.set_xlabel("fraction of the counts forgotten per promise (dotted: how often people change)")
    ax.set_ylabel("log loss above the exact filter")
    ax.set_title("The best forgetting rate (ringed) is faster than the rate of change", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper center", ncol=1, fontsize=9, bbox_to_anchor=(0.5, -0.18))
    save(fig, out, "forgetting-rate.svg")


# --- diagrams for the overview post ---

def canvas(width, height, xmax, ymax):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title, sub=None, colour=BLUE, fill="#eaf2fc"):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", linewidth=1.4, edgecolor=colour, facecolor=fill))
    if sub:
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", color=INK, fontsize=10, fontweight="bold")
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", color=MUTED, fontsize=8.5)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", color=INK, fontsize=10, fontweight="bold")


def arrow(ax, start, end, label=None, at=None, ha="center", rad=0.0):
    ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color=MUTED, linewidth=1.3, shrinkA=2, shrinkB=2,
                                                          connectionstyle=f"arc3,rad={rad}"))
    if label:
        lx, ly = at if at else ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        ax.text(lx, ly, label, ha=ha, va="center", color=INK, fontsize=8.5, bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))


def diagram_pieces(out):
    fig, ax = canvas(7.8, 5.6, 100, 72)
    warm, warm_fill, green, green_fill, grey = ORANGE, "#fdeee7", AQUA, "#e6f6f0", "#f3f2ee"
    box(ax, 4, 60, 20, 9, "Borrower", colour=MUTED, fill=grey)
    box(ax, 28, 60, 20, 9, "Lender", colour=MUTED, fill=grey)
    box(ax, 76, 60, 22, 9, "Everyone holding", "reputation", colour=MUTED, fill=grey)
    box(ax, 4, 37, 44, 11, "A script (here: LoanScript)", "anyone can write one; it holds no special powers", colour=warm, fill=warm_fill)
    box(ax, 56, 37, 26, 11, "Claim token", "a tradable claim on the debt", colour=warm, fill=warm_fill)
    box(ax, 2, 12, 22, 12, "Promise log", "CalculusEngine")
    box(ax, 29, 13.5, 15, 9, "Oracle", "off-chain", colour=MUTED, fill=grey)
    box(ax, 49, 12, 24, 12, "Reputation", "scores and bonds; fades")
    box(ax, 78, 12, 20, 12, "Treasury", "payout fund", colour=green, fill=green_fill)

    arrow(ax, (14, 60), (14, 48), "authorise it,\nset its allowances", at=(14, 54))
    arrow(ax, (38, 60), (38, 48), "set its\nallowance", at=(38, 54))
    arrow(ax, (10, 37), (10, 24), "record promises,\nmove money", at=(11, 30.5))
    arrow(ax, (42, 37), (56, 24), "hold a bond: return it,\nor destroy it on default", at=(40, 30.5))
    arrow(ax, (48, 42.5), (56, 42.5), "on default", at=(52, 45.5))
    arrow(ax, (70, 37), (64, 24), "marks the defaulter\ndelinquent", at=(79, 30.5))
    arrow(ax, (24, 18), (29, 18))
    arrow(ax, (44, 18), (49, 18))
    arrow(ax, (13, 12), (88, 12), "a fee on every promise", at=(50, 3.2), rad=0.2)
    arrow(ax, (91, 24), (91, 60), "dividends, in\nproportion to\nreputation", at=(91, 52))
    save(fig, out, "rain-pieces.svg")


def diagram_loan(out):
    fig, ax = canvas(7.8, 4.1, 100, 54)
    grey = "#f3f2ee"
    box(ax, 2, 35, 20, 10, "Requested", "reputation bonded", colour=MUTED, fill=grey)
    box(ax, 40, 35, 20, 10, "Active")
    box(ax, 78, 35, 20, 10, "Repaid", colour=AQUA, fill="#e6f6f0")
    box(ax, 2, 9, 20, 10, "Cancelled", colour=MUTED, fill=grey)
    box(ax, 40, 9, 20, 10, "Defaulted", colour=ORANGE, fill="#fdeee7")
    box(ax, 78, 9, 20, 10, "Settled", colour=MUTED, fill=grey)
    arrow(ax, (22, 40), (40, 40), "lender pays the principal;\nthe promise to repay is\nrecorded; fee paid", at=(31, 49.5))
    arrow(ax, (60, 40), (78, 40), "repaid in time:\nbond returned,\nreputation earned", at=(69, 49.5))
    arrow(ax, (12, 35), (12, 19), "borrower withdraws:\nbond returned", at=(12, 27))
    arrow(ax, (50, 35), (50, 19), "deadline passes: bond destroyed,\nlender gets a claim token,\nborrower marked delinquent", at=(50, 27))
    arrow(ax, (60, 14), (78, 14), "borrower buys the claim back\nand burns it: no longer delinquent", at=(69, 3.5))
    save(fig, out, "rain-loan-lifecycle.svg")


def diagram_cycle(out):
    fig, ax = canvas(7.8, 3.6, 100, 46)
    box(ax, 2, 30, 20, 11, "A promise", "pays a fee: 1% of it", colour=MUTED, fill="#f3f2ee")
    box(ax, 38, 30, 22, 11, "Payout fund", "holds all fees", colour=AQUA, fill="#e6f6f0")
    box(ax, 76, 16, 22, 14, "Dividend", "each holder's share is\ntheir share of reputation", colour=AQUA, fill="#e6f6f0")
    box(ax, 2, 5, 20, 11, "If it is kept", "the promisor earns", colour=MUTED, fill="#f3f2ee")
    box(ax, 38, 5, 22, 11, "Reputation", "fades 3% each period")
    arrow(ax, (22, 35.5), (38, 35.5), "fee", at=(30, 38))
    arrow(ax, (60, 35.5), (80, 30), "3% of the fund\neach cycle", at=(72, 37.5))
    arrow(ax, (22, 10.5), (38, 10.5), "fee / price\nof a point", at=(30, 15))
    arrow(ax, (60, 10.5), (80, 16), "sets the shares", at=(72, 9.5))
    arrow(ax, (12, 30), (12, 16))
    save(fig, out, "rain-fees-and-reputation.svg")


# --- numbers ---

def fmt(x, digits=2):
    return f"{x:,.{digits}f}"


def pct(x, digits=0):
    return f"{100 * x:.{digits}f}%"


def numbers(keeper, peaks):
    df, fd, es, sy = results("default_frontier"), results("fee_dynamics"), results("exit_scam"), results("sybil")
    af, bd, sf, cr = results("anchored_fee"), results("bayes_decay"), results("surge_fixes"), results("current_rules")
    dc, ol, sv = results("dividend_concentration"), results("oracle_lag"), results("standing_value")
    n = {}

    # original rules
    n["orig_demo_safe_loan"] = fmt(df["part_c"]["demo_safe_loan"])
    n["orig_demo_oversize"] = fmt(df["part_c"]["oversize_factor"], 0)
    n["orig_formula_error"] = f"{max(r['relative_error'] for r in df['part_a']):.0e}"
    a1 = fd["results"]["A1_baseline"]
    n["keeper_max_value_over_fee"] = fmt(a1["max_value_over_fee"])
    n["keeper_exponent"] = fmt(a1["fee_exponent_fitted"])
    n["keeper_fee_after_first_update"] = f"{keeper['after_first_update']:.4f}"
    n["keeper_fee_at_300"] = f"{keeper['at_300']:.5f}"
    n["keeper_shock_ratio"] = fmt(fd["results"]["A4_shock"]["value_over_fee_at"]["50"], 1)
    n["free_identity_naive"] = fmt(sy["scenarios"]["naive (20 per point)"]["S1_free_mint"]["profit"], 0)
    n["free_identity_careful"] = fmt(sy["scenarios"]["careful (0.9 v per point)"]["S1_free_mint"]["profit"], 0)
    n["orig_scam_100_points"] = fmt(es["demo"]["profit_100_points"], 0)

    # anchoring and paying out
    b = af["results"]
    n["steady_value_over_cost"] = fmt(b["B2_pass_through"]["value_over_cost_at"]["650"], 3)
    n["yield_only_crossing"] = str(b["B1"]["first_cycle_farming_pays"])
    n["asreceived_start"] = fmt(peaks["paid out as received"]["start"])
    n["asreceived_surge_peak"] = fmt(peaks["paid out as received"]["surge_peak"])
    s = sf["results"]
    n["genesis_surge_peak"] = fmt(s["baseline"]["x10"]["peak"])
    n["genesis_surge_cycles"] = str(s["baseline"]["x10"]["cycles_above_one"])
    fund = s["smoothed, rho 0.03, no genesis"]
    n["fund_start"] = fmt(fund["startup"]["t0"], 3)
    n["fund_surge_peak"] = fmt(fund["x10"]["peak"], 3)
    n["fund_fall_trough"] = fmt(fund["/10"]["trough"], 3)
    n["fund_grant_peak"] = fmt(fund["grant"]["peak"])
    n["fund_fast_release_peak"] = fmt(s["smoothed, rho 0.3"]["x10"]["peak"])
    n["issuance_grant_peak"] = fmt(s["fixed issuance"]["grant"]["peak"])
    n["vesting10_steady"] = fmt(s["vesting 10"]["steady"])
    n["vesting10_surge_peak"] = fmt(s["vesting 10"]["x10"]["peak"])
    n["current_surge_peak"] = fmt(cr["B"]["x10"]["peak"], 3)
    n["current_farmer_promises"] = str(cr["B"]["x10 + farmer"]["farmer"]["promises"])

    # bonds, scams, identities under the current rules
    a = cr["A"]
    n["point_value"] = fmt(a["v"], 3)
    n["fees_per_unit_credit"] = fmt(a["fees_per_unit_of_credit"])
    n["demo_oversize"] = fmt(a["demo_oversize"], 0)
    n["demo_safe_loan"] = fmt(a["demo_safe_loan"])
    n["surplus_threshold"] = pct(a["surplus_threshold"], 2)
    scen = cr["D"]["scenarios"]
    n["no_rep_identity"] = fmt(scen["demo ratio (5.5)"]["none"]["profit"], 1)
    n["bought_identity_naive"] = fmt(scen["demo ratio (5.5)"]["bought"]["profit"], 0)
    n["bought_identity_careful"] = fmt(scen["careful (0.9 v)"]["bought"]["profit"])
    n["scaling_profit"] = fmt(cr["D"]["scaling"]["1000"]["profit_per_identity"], 0)

    # the account of a default
    def row(case, rung):
        return sv["accounts"][case]["at"][str(rung)]
    shut3, again3, again6 = "sigma=0.03, shut out for good", "sigma=0.03, can start again", "sigma=0.06, can start again"
    n["account_error"] = pct(max(c["error_over_kept"] for c in sv["checks"]), 2)
    n["r40_loan"] = fmt(row(shut3, 40)["loan"], 0)
    n["r40_dividends"] = fmt(row(shut3, 40)["dividends"], 0)
    n["r40_access"] = fmt(row(shut3, 40)["access"], 0)
    n["shut3_safe"] = f"{sv['accounts'][shut3]['first_safe_rung']} to {sv['accounts'][shut3]['last_safe_rung']}"
    n["again3_safe"] = f"{sv['accounts'][again3]['first_safe_rung']} to {sv['accounts'][again3]['last_safe_rung']}"
    n["again6_first_safe"] = str(sv["accounts"][again6]["first_safe_rung"])
    n["again6_gain_at_81"] = fmt(row(again6, 81)["gain"], 0)
    n["again6_gain_at_120"] = fmt(-row(again6, 120)["gain"], 0)
    n["again6_dividends_81"] = fmt(row(again6, 81)["dividends"], 0)
    n["again6_dividends_120"] = fmt(row(again6, 120)["dividends"], 0)
    n["dividend_share_cap"] = pct(sv["accounts"][shut3]["dividend_share_at"]["120"])
    n["dividend_share_r40"] = pct(sv["accounts"][shut3]["dividend_share_at"]["40"])
    n["cap_stay_value"] = fmt(row(shut3, 120)["access"], 0)
    n["cap_kept"] = fmt(row(shut3, 120)["kept"], 0)

    # who holds reputation
    for decay, key in (("0.03", "d03"), ("0.005", "d005"), ("0.0", "d0")):
        r = dc["results"][decay]
        n[f"late_400_{key}"] = fmt(r["late_over_early_400"]["mean"])
        n[f"late_800_{key}"] = fmt(r["late_over_early_800"]["mean"])
        n[f"unreliable_{key}"] = fmt(r["unreliable_standing_800"]["mean"])
    r = dc["results"]["0.03"]
    n["gini_reputation"] = fmt(r["gini_reputation"]["mean"], 3)
    n["gini_activity"] = fmt(r["gini_activity"]["mean"], 3)
    n["reliable_dividends_over_fees"] = fmt(r["reliable_dividends_over_fees"]["mean"])
    n["unreliable_dividends_over_fees"] = fmt(r["unreliable_dividends_over_fees"]["mean"])
    n["top_tenth_reputation"] = pct(r["top_tenth_reputation_share"]["mean"])
    n["top_tenth_activity"] = pct(r["top_tenth_activity_share"]["mean"])

    # oracle lag
    for lag in ("1", "3", "12"):
        n[f"lag{lag}_newcomer"] = pct(1 - ol["results"][lag]["newcomer_relative"])
        n[f"lag{lag}_defaulter"] = pct(ol["results"][lag]["defaulter_relative"] - 1, 1)

    # decaying counts against the exact filter
    for hazard, key in (("0.005", "h005"), ("0.02", "h02"), ("0.05", "h05")):
        res = bd["results"][hazard]
        s_ = res["summary"]
        best = res["best_gamma_by_seed"][0]
        n[f"gap_matched_{key}"] = pct(sum(res["gap_closed"]) / len(res["gap_closed"]))
        n[f"best_gamma_{key}"] = str(best)
        n[f"gap_best_{key}"] = pct((s_["static"]["mean"] - s_[f"gamma={best}"]["mean"]) / (s_["static"]["mean"] - s_["exact"]["mean"]))
    n["static_loss_h05"] = fmt(bd["results"]["0.05"]["summary"]["static"]["mean"], 4)
    n["prior_loss_h05"] = fmt(bd["results"]["0.05"]["summary"]["prior"]["mean"], 4)

    # a manufactured record, and what a reader's trust does to it
    co = results("collusion")
    n["wash_cost"] = pct(co["A"][1]["share_of_amount"], 3)
    n["naive_bank_due"] = fmt(co["B"][1]["simulated_due"], 0)
    n["naive_bank_profit"] = fmt(co["B"][1]["simulated_profit"], 0)
    fine = {r["trust"]: r["multiple"] for r in co["F"]["fine_search"]}
    n["half_trust_multiple"] = fmt(fine[0.5])
    n["trust99_multiple"] = fmt(fine[0.99], 1)
    n["trust999_multiple"] = fmt(fine[0.999], 0)
    n["sybil20_multiple"] = fmt([r for r in co["D"] if r["trust"] == 0.5][0]["multiple"], 0)
    honest = {r["trust"]: r for r in co["E"]}
    n["portable_99"] = fmt(honest[0.99]["due"], 0)
    n["portable_999"] = fmt(honest[0.999]["due"], 0)
    n["portable_full"] = fmt(honest[1.0]["due"], 0)
    n["portable_99_rungs"] = fmt(honest[0.99]["rungs_to_reclimb"], 0)
    safe = {r["fee_rate"]: r["safe_trust"] for r in co["G"]}
    n["safe_trust_1pct"] = pct(safe[0.01], 1)
    n["safe_trust_5pct"] = pct(safe[0.05], 0)
    n["safe_trust_ratio"] = fmt(safe[0.01] / 0.01, 1)
    many = [r for r in co["F"]["confederates_for_100x"] if r["trust"] == 0.01][0]
    n["small_trust_confederates"] = str(many["confederates"])
    n["small_trust_loss"] = fmt(-many["simulated_profit"], 0)

    # the first loan
    fl = results("first_loan")
    n["repeat_value"] = fmt(fl["repeat_value"], 3)
    n["first_loan_loses_above"] = pct(fl["share_bounds"]["first_loan_loses_above"], 1)
    capped = {r["share"]: r for r in fl["follow_up"]["capped_first_loan"]["rows"]}
    for share, key in ((0.1, "10"), (0.2, "20"), (0.3, "30")):
        n[f"first_due_{key}"] = fmt(capped[share]["best_first_due"], 1)
    n["first_alone_20"] = fmt(-capped[0.2]["first_loan_alone"], 1)
    n["first_value_20"] = fmt(capped[0.2]["value"], 1)
    n["risk_ladder_value"] = fmt(-fl["policies"]["accept 10% risk on every loan (each 1.089 times the last)"]["simulated"], 0)
    n["repeat_floor_value"] = fmt(fl["policies"]["repeat the floor"]["simulated"], 1)
    n["growth_tail_5"] = fmt(fl["growth"][0]["largest_tail_index_with_growth"])
    idc = fl["follow_up"]["identity_then_climb"][0]
    n["identity_start"] = fmt(idc["start"], 1)
    n["identity_climb_value"] = fmt(idc["value_climbing"], 1)

    # vouching and graduation
    vo, gr = results("vouching"), results("graduation")
    n["vouch_naive_gain"] = fmt([r for r in vo["A"] if r["bank"] == "naive"][0]["gain_per_fake_borrower"], 0)
    n["vouch_burn_loss"] = fmt([r for r in vo["B"] if r["fake_borrowers"] == 20 and r["guarantees_count_against_the_guarantor"]][0]["bank_loss"], 0)
    n["vouch_burn_loss_uncounted"] = fmt([r for r in vo["B"] if r["fake_borrowers"] == 20 and not r["guarantees_count_against_the_guarantor"]][0]["bank_loss"], 0)
    costs = {r["opportunist_share"]: r["formula"] for r in vo["C"]["vouch_cost"]}
    n["vouch_cost_sure"], n["vouch_cost_10"], n["vouch_cost_50"] = fmt(costs[0.0], 0), fmt(costs[0.1], 0), fmt(costs[0.5], 0)
    n["vouch_surplus_threshold"] = pct(vo["C"]["surplus_threshold"], 1)
    worth = {r["surplus_rate"]: r for r in vo["C"]["borrower"]}
    n["vouch_net_with"], n["vouch_net_alone"] = fmt(worth[0.06]["with_guarantor"], 0), fmt(worth[0.06]["alone"], 0)
    n["guaranteed_round_cost"] = fmt(gr["one_guaranteed_round"]["simulated_cost"], 0)
    n["graduation_strategies"] = str(gr["rule"]["strategies"])
    n["graduation_control_loss"] = fmt(gr["controls"]["evidence alone"]["best"]["gain"], 0)
    n["graduation_cycles"] = str(gr["newcomer"]["with_guarantor"]["cycles_to_graduate"])
    n["graduation_guarantor_cost"] = fmt(gr["newcomer"]["with_guarantor"]["guarantor_expected_cost"], 0)
    n["graduation_offer_40"] = fmt(gr["newcomer"]["with_guarantor"]["offers"][40], 0)
    n["credit_per_point"] = fmt(gr["per_point"]["credit_per_point"], 3)
    n["sunk_fee_share"] = pct(gr["parameters"]["sunk_fee_share"], 1)

    # the three follow-ups: a borrower who chooses, the lender's side of graduating, a patient ring
    sb, ge, pr = results("strategic_borrower"), results("guarantor_exit"), results("patient_ring")
    n["return_threshold"] = pct(sb["return_threshold"]["formula"], 1)
    n["discount_plus_shock"] = pct(sb["return_threshold"]["discount_plus_shock"])
    n["capacity_ratio_15"] = fmt([r for r in sb["capacity"] if r["sigma"] == 0.15][0]["threshold_over_capacity"])
    gross = {r["interest"]: r["gross"] for r in sb["by_interest"]}
    n["gross_needed_5"], n["gross_needed_10"] = pct(gross[0.05], 1), pct(gross[0.10], 1)
    arr = ge["arrangements"]
    base = arr["a. guaranteed for ever"]["lender_value"]
    n["lender_loss_from_graduating"] = pct(1 - arr["b. graduating, unsecured at 5%"]["lender_value"] / base, 1)
    n["unsecured_rate_lender"] = pct(ge["premium_rate"], 2)
    n["unsecured_rate_borrower"] = pct(ge["borrower_indifferent_rate"], 2)
    n["graduation_cycles_premium"] = str(ge["graduation_by_unsecured_rate"][f"{100 * ge['premium_rate']:.2f}%"])
    at_five = pr["results"]["0.05"]["by_ring_rate"]
    n["patient_gain_4"] = pct(at_five["0.04"]["gain_over_fees_paid"], 1)
    n["patient_gain_0"] = pct(at_five["0.0"]["gain_over_fees_paid"])
    n["graduation_cycles_2pct"] = str(pr["results"]["0.02"]["graduation_cycles"])
    n["graduation_cycles_zero"] = str(pr["results"]["0.0"]["graduation_cycles"])

    # offline: accepting a payment that cannot be checked
    off = results("offline")
    arm = {name[0]: {r["payees"]: r for r in rows} for name, rows in off["exposure"].items()}
    n["off_places"] = str(off["parameters"]["places"])
    n["off_stranger_limit"] = fmt(off["parameters"]["stranger_limit"], 1)
    n["off_default_2"], n["off_default_5"], n["off_default_10"] = (pct(arm["A"][k]["default_rate"]) for k in (2, 5, 10))
    n["off_split_default_few"] = pct(arm["B"][4]["default_rate"])
    n["off_split_default_all"] = pct(arm["B"][5]["default_rate"])
    n["off_split_default_double"] = pct(arm["B"][10]["default_rate"])
    n["off_stale_total"] = fmt(off["stale_log"]["5 payees, log stale"], 1)
    growth = {g["case"]: g for g in off["growth"]}
    n["off_windows"] = str(off["parameters"]["windows"])
    n["off_growth_default"] = fmt(growth["default reading, 5 of 5 payees"]["limit_after"], 1)
    n["off_growth_concurrent"] = f'{growth["concurrent, 5 of 5, payees trust each other fully"]["limit_after"]:,.0f}'
    n["off_growth_hub"] = f'{growth["one hub, spent at 2 payees"]["limit_after"]:,.0f}'
    capped = growth["concurrent, 5 of 5, trust 0.9"]
    n["off_cap_09"] = fmt(capped["limit_after"], 0)
    n["off_cap_09_multiple"] = fmt(capped["limit_after"] / capped["limit_at_start"])
    n["off_cap_05"] = fmt(growth["concurrent, 5 of 5, trust 0.5"]["limit_after"], 1)
    wash = off["washing"]["0.9"]
    n["off_wash_default"] = fmt(wash["default reading, 1 confederate"])
    n["off_wash_concurrent"] = fmt(wash["concurrent, 2 confederates sharing the amount"])

    # what the fees could pay for
    fu = results("fee_use")
    rules = {name.split(".")[0] + ("b" if "someone else" in name else ""): r for name, r in fu["rules"].items()}
    n["fu_rebate"] = pct(fu["parameters"]["dividend_share"], 1)
    n["fu_wash_dividend"], n["fu_wash_burn"] = pct(rules["1"]["wash_cost"], 3), pct(rules["2"]["wash_cost"])
    n["fu_safe_dividend"], n["fu_safe_burn"] = pct(rules["1"]["safe_trust"], 1), pct(rules["2"]["safe_trust"], 1)
    n["fu_wash_work"] = pct(rules["5"]["wash_cost"], 2)
    ring = [r for r in fu["insurance"] if r["fake_ratio"] == 10.0][0]
    n["fu_insurance_ring_share"] = pct(ring["ring_share_of_pool"])
    n["fu_insurance_recover"] = pct(ring["honest_recover_share_of_loss"], 1)
    n["fu_insurance_recover_before"] = pct(fu["insurance"][0]["honest_recover_share_of_loss"])
    n["fu_identity_share"] = pct([r for r in fu["per_identity"] if r["identities_per_honest_identity"] == 10.0][0]["ring_share_of_revenue"])
    n["fu_forfeit"] = pct(fu["forfeit_as_share_of_amount_due"]["simulated"], 1)

    # the ladder's bounds (i = r = 5%, surplus 3%; risk 10%, shocks 2%, tail index 1)
    n["k_screen"] = fmt(ladder.screening_growth_factor(0.10, 1.0, 0.02), 3)
    n["k_stay"] = fmt(ladder.incentive_growth_factor(0.05, 0.03, 0.05), 3)
    n["doubling_risk"] = pct(1 - 0.98 / 2)
    return n


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    keeper = keeper_fee(out)
    peaks = payout_designs(out)
    default_by_rung(out)
    forgetting(out)
    diagram_pieces(out)
    diagram_loan(out)
    diagram_cycle(out)
    stamp = run_provenance()
    lines = ["# Generated by experiments/blog/make_assets.py in the rain repository. Do not edit by hand.",
             f"# Source commit {stamp['commit_short']} (dirty: {stamp['dirty']}), {stamp['utc']}.",
             f"commit: \"{stamp['commit_short']}\""]
    lines += [f"{key}: \"{value}\"" for key, value in numbers(keeper, peaks).items()]
    # Tallied by hand on 2026-11-20 from the outcome tables in the twenty experiment READMEs.
    lines += ['predictions_total: "126"', 'predictions_held: "93"', 'predictions_partly: "22"', 'predictions_wrong: "11"']
    (out / "rain.yml").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
