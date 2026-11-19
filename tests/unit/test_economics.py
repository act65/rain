"""
Claims tested: the closed forms in rain.economics are consistent with each other
and with the protocol rules they are derived from.
"""
import math

import pytest
from hypothesis import given, settings, strategies as st

from rain import economics as ec

V = 0.4  # value of a point, for the examples


def test_constants_match_the_oracle_rules():
    assert (ec.REP_GAIN, ec.REP_LOSS) == (25.0, 100.0)


def test_point_value_and_keeper_fee():
    # 500 per cycle over 375 points, discounted at 10% per cycle: 13.33 per point.
    # The original keeper charged margin x value x points earned: 1.5 x 13.33 x 25 = 500.
    v = ec.point_value(500, 375, 0.1)
    assert v == pytest.approx(40 / 3)
    assert ec.keeper_fee(v, 1.5) == pytest.approx(500)


@pytest.mark.parametrize("reputation,bond,expected", [
    (1000, 200, 200 + 100 + 25),   # bond + full flat penalty + forgone reward
    (150, 100, 100 + 50 + 25),     # penalty clamped at what is left
    (100, 100, 100 + 0 + 25),      # everything bonded: the flat penalty has nothing to take
    (1000, 0, 0 + 100 + 25),
])
def test_reputation_at_stake(reputation, bond, expected):
    assert ec.reputation_at_stake(reputation, bond) == expected


def test_earning_reputation_is_a_net_cost_when_margin_exceeds_one():
    # With no surplus from borrowing, each further loan loses (margin - 1) * v * g
    assert ec.continuation_value(1000, 0.0, V, 1.5, 0.05) == pytest.approx(-(0.5 * V * 25) / 0.05)
    assert ec.continuation_value(1000, 0.0, V, 1.0, 0.05) == 0


def test_max_safe_loan_without_surplus_is_the_value_of_reputation_at_stake():
    p = ec.max_safe_loan(0.05, 1000, 200, V)
    assert p == pytest.approx(V * 325 / 1.05)
    assert ec.default_gain(p, 0.05, 1000, 200, V) == pytest.approx(0, abs=1e-9)
    assert ec.default_gain(p * 1.01, 0.05, 1000, 200, V) > 0 > ec.default_gain(p * 0.99, 0.05, 1000, 200, V)


def test_max_safe_loan_with_surplus_counts_future_access():
    kwargs = dict(surplus_rate=0.03, margin=1.5, r=0.05)
    p = ec.max_safe_loan(0.05, 3000, 1000, V, **kwargs)
    assert p == pytest.approx((V * 1125 - 0.5 * V * 25 / 0.05) / (1.05 - 0.6))
    assert p > ec.max_safe_loan(0.05, 3000, 1000, V)
    assert ec.continuation_value(p, 0.03, V, 1.5, 0.05) > 0
    assert ec.default_gain(p, 0.05, 3000, 1000, V, **kwargs) == pytest.approx(0, abs=1e-9)


def test_small_surplus_does_not_help_when_access_is_not_worth_its_fees():
    # At this loan size the surplus from borrowing is less than the net fee per loan
    kwargs = dict(surplus_rate=0.03, margin=1.5, r=0.05)
    assert ec.max_safe_loan(0.05, 1000, 200, V, **kwargs) == ec.max_safe_loan(0.05, 1000, 200, V)


def test_max_safe_loan_is_unbounded_when_access_alone_deters():
    kwargs = dict(surplus_rate=0.06, r=0.05)
    assert ec.max_safe_loan(0.05, 1000, 200, V, **kwargs) == math.inf
    for principal in (1, 50, 100, 1_000, 10**9):
        assert ec.default_gain(principal, 0.05, 1000, 200, V, **kwargs) <= 0


def test_high_surplus_still_leaves_small_loans_unsafe_when_little_reputation_is_at_stake():
    # Almost nothing bonded: loans too small for access to be worth protecting are defaulted on,
    # while large loans are safe.
    kwargs = dict(surplus_rate=0.06, r=0.05, rep_loss=0.0, rep_gain=25.0)
    p = ec.max_safe_loan(0.05, 1000, 1, V, **kwargs)
    assert p == pytest.approx(V * 26 / 1.05)
    assert ec.default_gain(2 * p, 0.05, 1000, 1, V, **kwargs) > 0
    assert ec.default_gain(10**6, 0.05, 1000, 1, V, **kwargs) < 0


def test_worthless_reputation_and_no_surplus_backs_no_loan():
    assert ec.max_safe_loan(0.05, 1000, 1000, 0.0) == 0
    assert ec.default_gain(1.0, 0.05, 1000, 1000, 0.0) > 0


@settings(max_examples=300, deadline=None)
@given(
    i=st.floats(0, 0.5), rep=st.floats(1, 1e5), bond_frac=st.floats(0, 1), v=st.floats(0.001, 100),
    sigma=st.floats(0, 0.04), m=st.floats(1, 3), r=st.floats(0.05, 0.5),
)
def test_property_default_pays_exactly_above_the_safe_loan(i, rep, bond_frac, v, sigma, m, r):
    kw = dict(surplus_rate=sigma, margin=m, r=r)
    bond = bond_frac * rep
    p = ec.max_safe_loan(i, rep, bond, v, **kw)
    assert p > 0 and math.isfinite(p)  # sigma / r < 1 + i throughout this range
    scale = max(1.0, p)
    assert ec.default_gain(p * 1.001 + 1e-6, i, rep, bond, v, **kw) > -1e-9 * scale
    assert ec.default_gain(p * 0.999, i, rep, bond, v, **kw) < 1e-9 * scale


def test_exit_scam_thresholds():
    # Turning existing reputation pays exactly when lenders advance more than v per point
    assert ec.exit_scam_profit(V, V, 100) == pytest.approx(0)
    assert ec.exit_scam_profit(1.1 * V, V, 100) > 0 > ec.exit_scam_profit(0.9 * V, V, 100)
    # Buying reputation in order to burn it pays exactly when they advance more than margin * v
    base = ec.exit_scam_profit(1.5 * V, V, 100)
    assert ec.exit_scam_profit(1.5 * V, V, 100, loans_to_build=10) == pytest.approx(base)
    assert ec.exit_scam_profit(1.6 * V, V, 100, loans_to_build=10) > ec.exit_scam_profit(1.6 * V, V, 100)
    assert ec.exit_scam_profit(1.4 * V, V, 100, loans_to_build=10) < ec.exit_scam_profit(1.4 * V, V, 100)


def test_exit_scam_for_a_disposable_identity_has_no_forgone_dividends():
    held = ec.exit_scam_profit(2.0, V, 100)
    disposable = ec.exit_scam_profit(2.0, V, 100, held_alternative=False, identity_cost=7)
    assert disposable == pytest.approx(held + V * 100 - 7)


def test_fee_feedback_exponent():
    assert ec.fee_feedback_exponent(1.5, 0.004, 0.05) == pytest.approx(0.12)


# --- Current rules: fixed price per point, decay, fees paid out ---

KAPPA, R, DELTA, PHI, FMIN = 0.04, 0.05, 0.03, 0.01, 0.1
CURRENT = dict(point_price=KAPPA, r=R, decay_rate=DELTA, fee_rate=PHI, min_fee=FMIN)


def test_current_point_value():
    assert ec.current_point_value(KAPPA, R, DELTA) == pytest.approx(0.015)
    assert ec.current_point_value(KAPPA, R, DELTA) < KAPPA  # always worth less than it cost


def test_current_default_gain_by_hand():
    # Loan 1000 at 5%: due 1050, fee 10.5. Reputation 5000, bond 2000: at stake 2100 points worth 31.5.
    # Forgone reward: 10.5 * 0.375 = 3.9375. No surplus, so no access value.
    gain = ec.current_default_gain(1000, 0.05, 5000, 2000, **CURRENT)
    assert gain == pytest.approx(1050 - 31.5 - 3.9375)
    # With a 2% surplus: access is worth (20 - 10.5 * 0.625) / 0.05 = 268.75
    assert ec.current_default_gain(1000, 0.05, 5000, 2000, surplus_rate=0.02, **CURRENT) == pytest.approx(gain - 268.75)


@settings(max_examples=300, deadline=None)
@given(i=st.floats(0, 0.3), rep=st.floats(1, 1e5), bond_frac=st.floats(0, 1), sigma=st.floats(0, 0.045),
       phi=st.floats(0.001, 0.05), fmin=st.floats(0, 1))
def test_property_current_max_safe_loan_is_where_default_starts_to_pay(i, rep, bond_frac, sigma, phi, fmin):
    kw = dict(point_price=KAPPA, r=R, decay_rate=DELTA, fee_rate=phi, min_fee=fmin, surplus_rate=sigma)
    bond = bond_frac * rep
    p = ec.current_max_safe_loan(i, rep, bond, **kw)
    assert p >= 0 and math.isfinite(p)  # sigma / r < 1 throughout, so a large enough loan always tempts
    scale = max(1.0, p)
    assert ec.current_default_gain(p * 1.001 + 1e-6, i, rep, bond, **kw) > -1e-9 * scale
    for fraction in (0.999, 0.5, 0.1):  # safe all the way down, not just at the boundary
        assert ec.current_default_gain(p * fraction, i, rep, bond, **kw) < 1e-9 * scale


def test_current_max_safe_loan_unbounded_when_access_outweighs_any_repayment():
    assert ec.current_max_safe_loan(0.05, 5000, 2000, surplus_rate=0.06, **CURRENT) == math.inf
    assert ec.current_default_gain(10**9, 0.05, 5000, 2000, surplus_rate=0.06, **CURRENT) < 0


def test_current_exit_scam_thresholds():
    v = ec.current_point_value(KAPPA, R, DELTA)
    args = dict(point_price=KAPPA, r=R, decay_rate=DELTA)
    assert ec.current_exit_scam_profit(v, existing_reputation=100, **args) == pytest.approx(0)
    assert ec.current_exit_scam_profit(KAPPA, existing_reputation=0, bought_reputation=500, **args) == pytest.approx(0)
    # between v and the point price: turning existing reputation pays, buying more does not
    mid = (v + KAPPA) / 2
    base = ec.current_exit_scam_profit(mid, existing_reputation=100, **args)
    assert base > 0 and ec.current_exit_scam_profit(mid, existing_reputation=100, bought_reputation=500, **args) < base
