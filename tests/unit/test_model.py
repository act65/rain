"""
Claims tested: the Economy model applies the protocol's rules (unit level). Its
agreement with the real contracts is tested in tests/test_model_vs_contracts.py.
"""
import pytest

from rain import economics as ec
from rain.model import Economy


@pytest.fixture
def eco():
    e = Economy(fee=1.0, yield_rate=0.1)
    for name in ("alice", "bob", "carol"):
        e.add_agent(name, money=10_000, reputation=1_000)
    return e


def total_money(e):
    return sum(a.money for a in e.agents.values()) + e.treasury


def test_repaid_loan(eco):
    before = total_money(eco)
    loan = eco.loan("bob", "alice", principal=100, interest=5, bond=200)
    assert eco.agents["bob"].staked == 200 and eco.agents["bob"].liquid_reputation == 800
    eco.repay_loan(loan)
    bob, alice = eco.agents["bob"], eco.agents["alice"]
    assert (bob.money, alice.money, eco.treasury) == (10_000 - 5 - 1, 10_005, 1)
    assert (bob.reputation, bob.staked, bob.delinquent) == (1_025, 0, False)
    assert alice.reputation == 1_000  # lending is not a promise
    assert total_money(eco) == before  # money only moves


def test_defaulted_loan(eco):
    loan = eco.loan("bob", "alice", principal=100, interest=5, bond=200)
    eco.default_loan(loan)
    bob = eco.agents["bob"]
    assert bob.money == 10_000 + 100 - 1
    assert bob.reputation == 1_000 - 200 - 100
    assert bob.staked == 0 and bob.delinquent
    with pytest.raises(ValueError, match="delinquent"):
        eco.request_loan("bob", "carol", 1)


def test_penalties_are_clamped_at_zero(eco):
    loan = eco.loan("bob", "alice", principal=1, bond=950)
    eco.default_loan(loan)
    assert eco.agents["bob"].reputation == 0  # 1000 - 950 - min(100, 50)


def test_delinquent_agent_earns_nothing_until_resolved(eco):
    other = eco.loan("bob", "carol", principal=10, bond=10)
    bad = eco.loan("bob", "alice", principal=100, interest=5, bond=10)
    eco.default_loan(bad)
    rep = eco.agents["bob"].reputation
    eco.repay_loan(other)
    assert eco.agents["bob"].reputation == rep  # no reward while delinquent
    eco.resolve_default(bad)
    assert not eco.agents["bob"].delinquent
    assert eco.agents["alice"].money == 10_000 - 100 + 105
    assert eco.agents["bob"].reputation == rep  # resolution refunds nothing


def test_cancel_returns_the_bond_and_costs_nothing(eco):
    loan = eco.request_loan("bob", "alice", 100, bond=300)
    eco.cancel_loan(loan)
    assert eco.agents["bob"].staked == 0 and eco.treasury == 0
    with pytest.raises(ValueError):
        eco.fund_loan(loan)


def test_rules_that_raise(eco):
    with pytest.raises(ValueError, match="yourself"):
        eco.request_loan("bob", "bob", 1)
    with pytest.raises(ValueError, match="liquid"):
        eco.request_loan("bob", "alice", 1, bond=1_001)
    with pytest.raises(ValueError, match="cannot pay"):
        eco.loan("bob", "alice", principal=10_001)


def test_dividend_is_the_yield_split_pro_rata_and_capital_is_kept(eco):
    eco.agents["carol"].reputation = 2_000
    eco.donate(400)
    paid = eco.pay_dividend()
    assert paid == 40 and eco.treasury == 400
    assert [eco.agents[n].dividends_received for n in ("alice", "bob", "carol")] == [10, 10, 20]
    assert eco.dividend_history == [40]


def test_delinquent_agents_still_collect_dividends(eco):
    eco.default_loan(eco.loan("bob", "alice", principal=1, bond=0))
    eco.donate(1_000)
    eco.pay_dividend()
    assert eco.agents["bob"].dividends_received > 0


def test_fee_keeper_matches_the_closed_form(eco):
    assert eco.update_fee() == 1.0  # unchanged until there has been a dividend
    eco.donate(300)
    for _ in range(4):
        eco.pay_dividend()
    fee = eco.update_fee(margin=1.5, r=0.05)
    assert fee == pytest.approx(ec.keeper_fee(ec.point_value(30, 3_000, 0.05), 1.5))
    assert eco.fee == fee


def test_kept_promises_in_bulk(eco):
    eco.kept_promises("alice", count=10)
    assert eco.agents["alice"].reputation == 1_250
    assert eco.treasury == 10 and eco.agents["alice"].fees_paid == 10


# --- The current rules, one switch at a time ---

def test_point_price_makes_the_reward_proportional_to_the_fee():
    e = Economy(fee=2.0, point_price=0.04)
    e.add_agent("a", money=100)
    e.add_agent("b", money=100)
    e.kept_promises("a", 3)
    assert e.agents["a"].reputation == pytest.approx(3 * 2.0 / 0.04)
    loan = e.loan("b", "a", principal=10)
    e.fee = 5.0  # the reward follows the fee that was actually paid
    e.repay_loan(loan)
    assert e.agents["b"].reputation == pytest.approx(2.0 / 0.04)


def test_decay_shrinks_reputation_after_each_dividend():
    e = Economy(yield_rate=0.1, decay_rate=0.25)
    e.add_agent("a", reputation=100)
    e.donate(50)
    e.stake("a", 40)
    assert e.pay_dividend() == 5 and e.agents["a"].dividends_received == 5  # paid on the full 100
    assert (e.agents["a"].reputation, e.agents["a"].staked) == (75, 30)  # the bond decays with the score
    e.pay_dividend()
    assert e.agents["a"].reputation == pytest.approx(56.25)


def test_pass_through_pays_fees_out_instead_of_keeping_them():
    e = Economy(fee=1.0, pass_through=True)
    e.add_agent("a", money=100, reputation=30)
    e.add_agent("b", money=0, reputation=10)
    e.kept_promises("a", 4)  # a now has 30 + 100 points
    assert e.treasury == 0 and e.fee_pool == 4
    e.grant(10)
    assert e.pay_dividend() == 14
    assert e.agents["b"].dividends_received == pytest.approx(14 * 10 / 140)
    assert e.fee_pool == 0 and e.pay_dividend() == 0


def test_supply_settles_at_the_steady_state_formula():
    e = Economy(fee=1.0, point_price=0.04, decay_rate=0.05, pass_through=True)
    e.add_agent("a", money=1e9, reputation=10)
    for _ in range(400):
        e.kept_promises("a", 100)
        e.pay_dividend()
    assert e.total_reputation == pytest.approx(ec.steady_state_supply(100, 0.04, 0.05), rel=1e-6)


def test_decaying_point_value_is_the_discounted_sum():
    d, r, delta = 0.002, 0.05, 0.03
    direct = sum(d * (1 - delta) ** k / (1 + r) ** (k + 1) for k in range(5000))
    assert ec.decaying_point_value(d, r, delta) == pytest.approx(direct)
    assert ec.pass_through_value_over_cost(r, delta) == pytest.approx(0.375)


def test_open_loans_bonds_decay_so_they_release_cleanly():
    e = Economy(decay_rate=0.1)
    e.add_agent("a", money=100, reputation=100)
    e.add_agent("b", money=100)
    loan = e.loan("a", "b", principal=10, bond=50)
    e.decay()
    assert e.agents["a"].staked == pytest.approx(45) and e.loans[loan].bond == pytest.approx(45)
    e.repay_loan(loan)
    assert e.agents["a"].staked == pytest.approx(0)


def test_fee_is_a_fraction_of_the_amount_with_a_minimum():
    e = Economy(fee=0.1, fee_rate=0.01)
    assert e.quote_fee(5) == 0.1 and e.quote_fee(1000) == 10 and e.quote_fee() == 0.1
    e.add_agent("a", money=1000)
    e.add_agent("b", money=1000)
    loan = e.loan("a", "b", principal=400, interest=100)
    assert e.loans[loan].fee_paid == 5 and e.treasury == 5


def test_superseded_genesis_rules_send_the_reserve_holders_share_to_a_fund():
    e = Economy.genesis_rules(min_fee=1.0, fee_rate=0.0, point_price=0.04, decay_rate=0.0,
                              reserve_release=0.1, genesis_reputation=75)
    e.add_agent("a", money=100, reputation=25)
    e.grant(40)
    assert e.pay_dividend() == 40
    assert e.agents["a"].dividends_received == 10 and e.reserve_fund == 30
    assert e.agents["treasury"].money == 0  # the reserve holder is never paid
    assert e.pay_dividend() == pytest.approx(3)  # a tenth of the fund, shared out again


def test_current_rules_reward_follows_the_fee_and_fees_are_paid_out_gradually():
    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    assert e.reserve_release == 0.03  # the release rate defaults to the decay rate
    e.add_agent("a", money=10_000)
    e.add_agent("b", money=10_000)
    e.repay_loan(e.loan("a", "b", principal=100, interest=5))
    assert e.agents["a"].reputation == pytest.approx(1.05 / 0.04)
    assert e.fee_pool == pytest.approx(1.05) and e.treasury == 0
    assert e.pay_dividend() == pytest.approx(0.03 * 1.05)
    assert e.reserve_fund == pytest.approx(0.97 * 1.05)
    assert e.agents["a"].dividends_received == pytest.approx(0.03 * 1.05)  # the only holder


def test_start_in_steady_state_pays_out_exactly_what_comes_in():
    e = Economy.current_rules(min_fee=1.0, fee_rate=0.0, point_price=0.04, decay_rate=0.03)
    e.add_agent("a", money=1e9, reputation=100 / 0.04 / 0.03)
    e.start_in_steady_state(fee_flow=100)
    for _ in range(50):
        assert e.pay_dividend() == pytest.approx(100)
        e.kept_promises("a", 100)
    assert e.total_reputation == pytest.approx(100 / 0.04 / 0.03)


def test_oracle_lag_delays_rewards_and_penalties_but_not_the_bond_or_the_flag():
    e = Economy(fee=1.0, oracle_lag=2)
    for name in ("a", "b", "bank"):
        e.add_agent(name, money=1000, reputation=500)
    e.repay_loan(e.loan("a", "bank", principal=10))
    bad = e.loan("b", "bank", principal=10, bond=200)
    e.default_loan(bad)
    # At once, on-chain: the bond is gone and b is delinquent. Not yet: a's reward, b's flat penalty.
    assert e.agents["a"].reputation == 500
    assert e.agents["b"].reputation == 300 and e.agents["b"].delinquent
    e.pay_dividend()
    assert (e.agents["a"].reputation, e.agents["b"].reputation) == (500, 300)  # one cycle: still waiting
    e.pay_dividend()
    e.pay_dividend()  # the oracle runs at the start of the cycle in which the updates fall due
    assert e.agents["a"].reputation == 525
    assert e.agents["b"].reputation == 200
    assert e.pending_updates == []


def test_under_the_current_rules_a_default_is_recorded_and_takes_only_the_bond():
    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    for name in ("b", "bank"):
        e.add_agent(name, money=1000, reputation=500)
    e.default_loan(e.loan("b", "bank", principal=200, interest=10, bond=120))
    b = e.agents["b"]
    assert b.reputation == pytest.approx(500 - 120)  # the bond, and no flat penalty
    assert b.broken == pytest.approx(2.1 / 0.04)  # the weight repaying would have earned
    assert b.delinquent
    e.pay_dividend()
    assert b.broken == pytest.approx(0.97 * 2.1 / 0.04)  # the record fades with the reputation
    assert b.reputation == pytest.approx(0.97 * 380)


def test_reward_depends_on_status_when_the_promise_was_kept_not_when_the_oracle_runs():
    e = Economy(fee=1.0, oracle_lag=1)
    for name in ("a", "bank"):
        e.add_agent(name, money=1000, reputation=500)
    other = e.loan("a", "bank", principal=10)
    e.repay_loan(e.loan("a", "bank", principal=10))  # kept while in good standing: reward pending
    e.default_loan(e.loan("a", "bank", principal=10))  # delinquent before the oracle runs
    e.repay_loan(other)  # kept while delinquent: no reward
    e.pay_dividend()
    e.pay_dividend()
    assert e.agents["a"].reputation == 500 + 25 - 100  # the first reward and the penalty, whatever the lag


# --- Untested proposals for damping surges (not in the contracts) ---

def test_fixed_issuance_shares_a_fixed_number_of_points_by_fees_paid():
    e = Economy(fee=1.0, fee_rate=0.01, issuance_per_cycle=1000, pass_through=True)
    for name in ("a", "b", "bank"):
        e.add_agent(name, money=10_000)
    e.repay_loan(e.loan("a", "bank", principal=300))  # fee 3
    e.repay_loan(e.loan("b", "bank", principal=100))  # fee 1 (the minimum)
    assert e.agents["a"].reputation == 0  # minted at the end of the cycle
    e.pay_dividend()
    assert (e.agents["a"].reputation, e.agents["b"].reputation) == (750, 250)
    e.repay_loan(e.loan("a", "bank", principal=50_00))
    e.pay_dividend()
    assert e.agents["a"].reputation == 1750  # the whole cycle's issue, however large the fee


def test_smooth_payout_releases_fees_gradually():
    e = Economy(fee=10.0, pass_through=True, smooth_payout=True, reserve_release=0.1)
    e.add_agent("a", money=100, reputation=1)
    e.kept_promises("a")
    assert e.pay_dividend() == pytest.approx(1.0) and e.reserve_fund == pytest.approx(9.0)
    assert e.pay_dividend() == pytest.approx(0.9)


def test_vesting_points_exist_but_do_not_earn_until_vested():
    e = Economy(fee=1.0, pass_through=True, vesting_cycles=2)
    e.add_agent("old", money=100, reputation=25)
    e.add_agent("new", money=100)
    e.kept_promises("new")
    assert e.agents["new"].reputation == 25 and e.agents["new"].earning_reputation == 0
    e.pay_dividend()
    assert e.agents["old"].dividends_received == 1.0 and e.agents["new"].dividends_received == 0
    e.kept_promises("old")
    e.pay_dividend()
    assert e.agents["new"].dividends_received == 0  # one more cycle to go
    e.kept_promises("old")
    e.pay_dividend()
    assert e.agents["new"].dividends_received > 0


# --- offline notes ---

def test_a_note_the_payer_can_cover_is_paid_and_the_payer_bears_the_fee():
    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    e.add_agent("payer", money=1000.0)
    e.add_agent("shop", money=50.0)
    assert e.settle_note("payer", "shop", 200.0, issued=-1)
    assert e.agents["payer"].money == pytest.approx(1000 - 200 - 2)
    assert e.agents["shop"].money == pytest.approx(250.0)
    assert e.agents["payer"].reputation == pytest.approx(2 / 0.04)
    entry = e.log[-1]
    assert (entry.promisor, entry.promisee, entry.amount, entry.kept, entry.created) == ("payer", "shop", 200.0, True, -1)


def test_a_double_spend_is_recorded_as_a_broken_promise_and_costs_the_payee_the_fee():
    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    e.add_agent("payer", money=250.0)
    e.add_agent("shop1", money=50.0)
    e.add_agent("shop2", money=50.0)
    assert e.settle_note("payer", "shop1", 200.0)
    assert not e.settle_note("payer", "shop2", 200.0)  # the same money, promised twice
    assert e.agents["shop2"].money == pytest.approx(50 - 2)
    assert e.agents["payer"].money == pytest.approx(250 - 202)
    assert e.agents["payer"].broken == pytest.approx(2 / 0.04)
    assert e.agents["payer"].delinquent
    assert [x.kept for x in e.log] == [True, False]
