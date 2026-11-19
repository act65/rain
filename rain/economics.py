"""
Closed-form economics of the Rain protocol: what reputation is worth, and when
breaking a promise pays.

The first part analyses the ORIGINAL rules (a flat reward per promise, a fee keeper, a
treasury that pays only its yield, no decay); the experiments that led to the current
rules use it. The last part covers the current rules (a fixed price per point, decay,
fees paid out).

Everything in the first part follows from four protocol facts:

  - a reputation point earns a pro-rata share of each dividend cycle;
  - a kept promise costs its promisor the protocol fee and earns `rep_gain` points;
  - a default destroys the bond, costs a further `rep_loss` points (clamped at the
    remaining score), forfeits the reward, and bars the defaulter from borrowing;
  - a delinquent user keeps collecting dividends on whatever reputation is left.

Conventions: time is in dividend cycles; `r` is the discount rate per cycle; a
payment at the end of each cycle forever is worth `payment / r` today. Money is in
currency units and reputation in points (floats; this module is for analysis).
"""

from __future__ import annotations

import math

from rain.reputation import REP_LOSS_ON_DEFAULT

REP_GAIN = 25.0  # points earned by a kept promise under the original rules (flat reward)
REP_LOSS = REP_LOSS_ON_DEFAULT / 10**18  # flat points lost on default, on top of the bond


def point_value(dividend_per_cycle: float, total_reputation: float, r: float) -> float:
    """v: the present value of the dividends one reputation point will collect."""
    return dividend_per_cycle / total_reputation / r


def keeper_fee(v: float, margin: float, rep_gain: float = REP_GAIN) -> float:
    """The per-promise fee the keeper sets when a point is worth `v`."""
    return margin * v * rep_gain


def reputation_at_stake(reputation: float, bond: float, rep_gain: float = REP_GAIN, rep_loss: float = REP_LOSS) -> float:
    """
    Points a borrower ends up without if they default instead of repaying:
    the bond, the flat penalty (at most what is left), and the reward not earned.
    """
    return bond + min(rep_loss, reputation - bond) + rep_gain


def continuation_value(principal: float, surplus_rate: float, v: float, margin: float, r: float, rep_gain: float = REP_GAIN) -> float:
    """
    X: the present value, to an honest borrower, of being allowed to keep borrowing
    `principal` every cycle. Each loan yields `surplus_rate * principal` (the return on
    the borrowed capital net of interest) and `rep_gain` points worth `v` each, and
    costs the fee `margin * v * rep_gain`. Because margin > 1 the reputation earned is
    worth less than the fee paid for it: earning reputation is a cost, not a motive.
    """
    per_cycle = surplus_rate * principal - (margin - 1) * v * rep_gain
    return per_cycle / r


def default_gain(
    principal: float, interest_rate: float, reputation: float, bond: float, v: float,
    surplus_rate: float = 0.0, margin: float = 1.5, r: float = 0.05,
    rep_gain: float = REP_GAIN, rep_loss: float = REP_LOSS,
) -> float:
    """
    Net present gain from defaulting on a loan instead of repaying it. Positive means
    default is the rational choice.

    The defaulter keeps `principal * (1 + interest_rate)`, loses the reputation at
    stake (worth `v` per point) and loses access to future loans. The honest
    alternative is the better of "repay and keep borrowing" and "repay and stop", so
    access only counts when it is worth something (X > 0).
    """
    kept = principal * (1 + interest_rate)
    lost_reputation = v * reputation_at_stake(reputation, bond, rep_gain, rep_loss)
    lost_access = max(0.0, continuation_value(principal, surplus_rate, v, margin, r, rep_gain))
    return kept - lost_reputation - lost_access


def max_safe_loan(
    interest_rate: float, reputation: float, bond: float, v: float,
    surplus_rate: float = 0.0, margin: float = 1.5, r: float = 0.05,
    rep_gain: float = REP_GAIN, rep_loss: float = REP_LOSS,
) -> float:
    """
    P*: the largest principal such that repaying is at least as good as defaulting for
    every loan up to that size.

    Three regimes:
      - access to future loans is worthless at P* (little or no surplus): P* is the
        value of the reputation at stake, discounted by the interest;
      - access is worth something and `surplus_rate / r < 1 + interest_rate`: P* is larger,
        because the defaulter also gives up the surplus from future loans;
      - `surplus_rate / r >= 1 + interest_rate`: the surplus from future borrowing outweighs
        any single repayment, so large loans are always safe. P* is infinite if small
        loans are safe too; otherwise there is a band of small loans, too small for
        access to be worth protecting, on which default pays, and P* is its lower edge.
    """
    stake_value = v * reputation_at_stake(reputation, bond, rep_gain, rep_loss)
    without_access = stake_value / (1 + interest_rate)
    net_fee = (margin - 1) * v * rep_gain  # what each further loan costs in fees beyond the reputation it earns

    denominator = 1 + interest_rate - surplus_rate / r
    if denominator <= 0:
        # Access is worth something for loans above net_fee / surplus_rate. If the loan
        # at that size is already safe, every loan is.
        break_even = net_fee / surplus_rate
        return math.inf if (1 + interest_rate) * break_even <= stake_value else without_access

    with_access = (stake_value - net_fee / r) / denominator
    if continuation_value(with_access, surplus_rate, v, margin, r, rep_gain) > 0:
        return with_access
    return without_access


def exit_scam_profit(
    lending_ratio: float, v: float, existing_reputation: float, loans_to_build: int = 0,
    margin: float = 1.5, rep_gain: float = REP_GAIN, identity_cost: float = 0.0, held_alternative: bool = True,
) -> float:
    """
    Profit from bonding all of one's reputation against loans and defaulting on them all,
    when lenders advance `lending_ratio` currency units per bonded point.

    The attacker may first buy more reputation by keeping `loans_to_build` promises at
    the keeper's fee (`margin * v` per point). `held_alternative` says whether the
    existing reputation would otherwise have been kept for its dividends (true for an
    established user, false for an identity created only to attack).

        profit = (ratio - v) * existing + loans * rep_gain * (ratio - margin * v) - identity_cost

    so turning existing reputation pays when ratio > v, and buying reputation to burn
    pays when ratio > margin * v.
    """
    built = loans_to_build * rep_gain
    extracted = lending_ratio * (existing_reputation + built)
    build_cost = loans_to_build * keeper_fee(v, margin, rep_gain)
    forgone = v * existing_reputation if held_alternative else 0.0
    return extracted - build_cost - forgone - identity_cost


def fee_feedback_exponent(margin: float, yield_rate: float, r: float) -> float:
    """
    c = margin * yield_rate / r. When dividends are the yield on accumulated fees and
    the keeper prices the fee from them, each promise multiplies the treasury-per-point
    ratio by (R + c * g) / (R + g), so treasury per point, the value of a point and the
    fee all scale as (total reputation) ** (c - 1): they decay if c < 1 and run away if c > 1.
    """
    return margin * yield_rate / r


# --- Current rules: a fixed price per point, decay, fees paid out (see experiments/anchored_fee) ---

def steady_state_supply(fee_flow: float, point_price: float, decay_rate: float) -> float:
    """
    Total reputation once issuance equals decay, when each unit of fees mints
    1 / point_price points and a fraction decay_rate of all points is lost per cycle
    (measured at the end of a cycle, after decay).
    """
    return fee_flow / point_price * (1 - decay_rate) / decay_rate


def decaying_point_value(dividend_per_point: float, r: float, decay_rate: float) -> float:
    """
    Present value of one point that earns `dividend_per_point` at the end of this cycle and
    then shrinks by `decay_rate` per cycle: d * sum_k ((1 - delta) / (1 + r))^k / (1 + r) = d / (r + delta).
    Decay acts as an extra discount rate.
    """
    return dividend_per_point / (r + decay_rate)


def pass_through_value_over_cost(r: float, decay_rate: float) -> float:
    """
    When fees are paid out to holders and supply is steady, a point costs point_price and is
    worth point_price * delta / (r + delta): always less than it cost, at any parameters.
    """
    return decay_rate / (r + decay_rate)


def current_point_value(point_price: float, r: float, decay_rate: float) -> float:
    """v under the current rules, once supply is steady: a point earns point_price * delta per cycle and decays."""
    return point_price * decay_rate / (r + decay_rate)


def current_default_gain(
    principal: float, interest_rate: float, reputation: float, bond: float,
    point_price: float, r: float, decay_rate: float, fee_rate: float, min_fee: float = 0.0,
    surplus_rate: float = 0.0, rep_loss: float = REP_LOSS,
) -> float:
    """
    Net present gain from defaulting instead of repaying, under the current rules (steady supply).

    The defaulter keeps the amount due. They lose the bond and the flat penalty (each point
    worth v = point_price * delta / (r + delta)), the reward for repaying (fee / point_price
    points, so worth fee * delta / (r + delta)), and access to future loans. Each future loan
    yields `surplus_rate * principal`, costs its fee and returns reputation worth
    delta / (r + delta) of that fee, so access is worth
    (surplus_rate * principal - fee * r / (r + delta)) / r when that is positive.
    """
    due = principal * (1 + interest_rate)
    fee = max(min_fee, fee_rate * due)
    v = current_point_value(point_price, r, decay_rate)
    stake_value = v * (bond + min(rep_loss, reputation - bond))
    forgone_reward = fee * decay_rate / (r + decay_rate)
    access = max(0.0, (surplus_rate * principal - fee * r / (r + decay_rate)) / r)
    return due - stake_value - forgone_reward - access


def current_max_safe_loan(
    interest_rate: float, reputation: float, bond: float,
    point_price: float, r: float, decay_rate: float, fee_rate: float, min_fee: float = 0.0,
    surplus_rate: float = 0.0, rep_loss: float = REP_LOSS,
) -> float:
    """
    The largest principal such that repaying is at least as good as defaulting for every loan
    up to that size (infinite if default never pays). `current_default_gain` is piecewise
    linear in the principal, so this walks its segments to the first crossing.
    """
    def gain(p):
        return current_default_gain(p, interest_rate, reputation, bond, point_price, r, decay_rate,
                                    fee_rate, min_fee, surplus_rate, rep_loss)

    # Kinks: where the proportional fee overtakes the minimum, and where access starts to be worth something.
    kinks = {0.0}
    if fee_rate > 0 and min_fee > 0:
        kinks.add(min_fee / (fee_rate * (1 + interest_rate)))
    if surplus_rate > 1e-12 and min_fee > 0:  # (a vanishing surplus never makes access worth its fee)
        kinks.add(min_fee * r / ((r + decay_rate) * surplus_rate))
    points = sorted(kinks)
    for lo, hi in zip(points, points[1:]):
        g_lo, g_hi = gain(lo), gain(hi)
        if g_lo <= 0 < g_hi:
            return lo + (hi - lo) * (-g_lo) / (g_hi - g_lo)
    last = points[-1]
    g_last = gain(last)
    slope = gain(last + 1.0) - g_last
    if g_last > 0:
        return last
    return last - g_last / slope if slope > 1e-12 else math.inf


def current_exit_scam_profit(
    lending_ratio: float, point_price: float, r: float, decay_rate: float,
    existing_reputation: float, bought_reputation: float = 0.0, held_alternative: bool = True,
) -> float:
    """
    Profit from bonding all reputation against loans and defaulting, when lenders advance
    `lending_ratio` per bonded point, under the current rules. Bought points cost
    `point_price` each in fees; existing points would otherwise be worth v each.

        profit = (ratio - v) * existing + (ratio - point_price) * bought
    """
    v = current_point_value(point_price, r, decay_rate)
    forgone = v * existing_reputation if held_alternative else 0.0
    return lending_ratio * (existing_reputation + bought_reputation) - point_price * bought_reputation - forgone
