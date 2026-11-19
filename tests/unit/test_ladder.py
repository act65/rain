"""
Claims tested: the ladder formulas follow from the models stated in rain.ladder
(checked by Monte Carlo and by direct summation).
"""
import math

import numpy as np
import pytest

from rain import ladder


def test_repay_probability_basic_cases():
    assert ladder.repay_probability(50, 100, 1.0) == 1.0  # already shown to repay more
    assert ladder.repay_probability(200, 100, 1.0) == 0.5
    assert ladder.repay_probability(200, 100, 2.0) == 0.25
    assert ladder.repay_probability(200, 100, 1.0, shock_rate=0.1) == pytest.approx(0.45)
    # Evidence that may be stale: a fresh draw is only known to exceed x_min
    assert ladder.repay_probability(200, 100, 1.0, still_same=0.5, x_min=10) == pytest.approx(0.5 * 0.5 + 0.5 * 0.05)


@pytest.mark.parametrize("tail_index,shock", [(0.5, 0.0), (1.0, 0.02), (2.0, 0.05)])
def test_repay_probability_matches_monte_carlo(tail_index, shock):
    rng = np.random.default_rng(0)
    x_min, repaid, due = 1.0, 3.0, 4.5
    cost = x_min * (1 - rng.random(2_000_000)) ** (-1 / tail_index)  # Pareto(x_min, a)
    survivors = cost[cost >= repaid]  # those who would have repaid `repaid`
    repays = (survivors >= due) & (rng.random(survivors.size) >= shock)
    assert repays.mean() == pytest.approx(ladder.repay_probability(due, repaid, tail_index, shock), abs=0.004)


def test_screening_growth_factor_hits_the_risk_tolerance():
    k = ladder.screening_growth_factor(0.10, 1.0, shock_rate=0.02)
    assert k == pytest.approx(0.98 / 0.90)
    assert 1 - ladder.repay_probability(k * 100, 100, 1.0, 0.02) == pytest.approx(0.10)
    assert ladder.screening_growth_factor(0.02, 1.0, 0.02) == 1.0  # no room to grow
    with pytest.raises(ValueError):
        ladder.screening_growth_factor(0.01, 1.0, 0.02)


def test_heavier_tail_or_more_tolerance_allows_faster_growth():
    assert ladder.screening_growth_factor(0.1, 0.5) > ladder.screening_growth_factor(0.1, 1.0) > ladder.screening_growth_factor(0.1, 2.0)
    assert ladder.screening_growth_factor(0.3, 1.0) > ladder.screening_growth_factor(0.1, 1.0)


@pytest.mark.parametrize("i,sigma,r", [(0.05, 0.03, 0.05), (0.10, 0.02, 0.08), (0.0, 0.10, 0.02)])
def test_incentive_growth_factor_is_the_point_of_indifference(i, sigma, r):
    k_min = ladder.incentive_growth_factor(i, sigma, r)

    def stay_minus_leave(k, horizon=20_000):
        # Staying: surplus sigma * P_j on every later loan, discounted. Leaving: keep P_0 (1 + i).
        stay = sum(sigma * (k / (1 + r)) ** j for j in range(1, horizon))
        return stay - (1 + i)

    assert stay_minus_leave(k_min) == pytest.approx(0, abs=1e-6)
    assert stay_minus_leave(k_min * 1.005) > 0 > stay_minus_leave(k_min * 0.995)


def test_no_surplus_means_no_incentive_to_stay():
    assert ladder.incentive_growth_factor(0.05, 0.0, 0.05) == math.inf


def test_exit_from_a_long_ladder_pays_only_if_it_grows_faster_than_interest():
    i = 0.05
    slow = ladder.exit_profit(100, 1.04, i, steps=400)
    fast = ladder.exit_profit(100, 1.06, i, steps=400)
    assert slow < 0 < fast
    # at k = 1 + i the interest paid cancels all but the first loan: the profit is the first rung
    assert ladder.exit_profit(100, 1.05, i, steps=400) == pytest.approx(100, rel=1e-6)


def test_exit_profit_by_hand():
    # loans 100, 110, 121: repay two (interest 10 + 11), default on the third
    assert ladder.exit_profit(100, 1.1, 0.1, steps=3) == pytest.approx(121 - 21)
    assert ladder.exit_profit(100, 1.1, 0.1, steps=1) == 100  # the first loan is pure exposure
    assert ladder.exit_profit(100, 1.1, 0.1, steps=3, fee=2) == pytest.approx(121 - 21 - 6)


def test_feasible_band():
    band = ladder.feasible_band(0.05, 0.03, 0.05, risk_tolerance=0.10, tail_index=1.0, shock_rate=0.02)
    assert band == pytest.approx((1.05 * 1.05 / 1.08, 1.05))
    # The band is non-empty exactly when the borrower's return on borrowed money, sigma + i, covers their discount rate
    assert ladder.feasible_band(0.05, 0.03, 0.09, 0.5, 1.0) is None
    assert ladder.feasible_band(0.05, 0.04, 0.09, 0.5, 1.0) is not None


# --- The account of a default on a ladder ---

LADDER = dict(first_loan=100, growth=1.05, cap=5000, interest_rate=0.05, r=0.05,
              fee_rate=0.01, min_fee=0.1, point_price=0.04, decay_rate=0.03)


def test_account_of_the_first_rung_by_hand():
    a = ladder.ladder_default_account(0, surplus_rate=0.03, restart=False, horizon=2, **LADDER)
    # Kept: 105. Reputation so far: none; the reward forgone is 1.05 / 0.04 points worth 0.015 each.
    assert a["kept"] == 105 and a["reputation"] == 0
    assert a["dividends"] == pytest.approx(1.05 * 0.375)
    # One future loan in a two-cycle horizon: 105 at rung 1, worth 3.15 less 62.5% of its 1.1025 fee, discounted once
    assert a["access"] == pytest.approx((0.03 * 105 - 1.1025 * 0.625) / 1.05)
    assert a["gain"] == pytest.approx(a["kept"] - a["dividends"] - a["access"])


def test_reputation_held_is_the_decayed_sum_of_rewards():
    a = ladder.ladder_default_account(3, surplus_rate=0.0, restart=False, **LADDER)
    fees = [0.01 * 100 * 1.05**m * 1.05 for m in range(3)]
    assert a["reputation"] == pytest.approx(sum(f / 0.04 * 0.97 ** (3 - m) for m, f in enumerate(fees)))


def test_being_able_to_start_again_makes_default_cheaper():
    banned = ladder.ladder_default_account(40, surplus_rate=0.03, restart=False, **LADDER)
    reborn = ladder.ladder_default_account(40, surplus_rate=0.03, restart=True, **LADDER)
    costly = ladder.ladder_default_account(40, surplus_rate=0.03, restart=True, identity_cost=200, **LADDER)
    assert banned["access"] > costly["access"] > reborn["access"] > 0
    assert costly["access"] == pytest.approx(reborn["access"] + 200)
    assert banned["dividends"] == reborn["dividends"]


def test_other_value_of_standing_counts_one_for_one():
    base = ladder.ladder_default_account(40, surplus_rate=0.03, **LADDER)
    more = ladder.ladder_default_account(40, surplus_rate=0.03, other_value=500, **LADDER)
    assert more["gain"] == pytest.approx(base["gain"] - 500)


def test_no_surplus_means_access_is_worth_nothing_or_less():
    a = ladder.ladder_default_account(40, surplus_rate=0.0, restart=False, **LADDER)
    assert a["access"] < 0  # carrying on only costs fees; the honest alternative is to stop
