"""
Claims tested: `rain.record.weigh` counts each kept promise at the reader's credence in it and
each broken one in full; the threshold belief is the exact posterior of the model stated in
rain.record (checked by Monte Carlo); a reader who trusts everyone recovers `rain.ladder`.
"""
import numpy as np
import pytest

from rain import ladder
from rain.model import Economy
from rain.record import (
    Entry, by_fee, largest_amount_due, repay_probability, threshold_survival, trusting, weigh,
)

A, FRIEND, BANK, OTHER = "0xA", "0xFriend", "0xBank", "0xOther"

LOG = [
    Entry(A, FRIEND, 1000, True, time=1, fee_paid=10),
    Entry(A, BANK, 100, True, time=2, fee_paid=1),
    Entry(A, BANK, 200, True, time=3, fee_paid=2),
    Entry(A, OTHER, 50, False, time=4, fee_paid=0.5),
    Entry(BANK, A, 999, True, time=4, fee_paid=9),  # A was the promisee here: not A's record
]


def test_a_reader_who_trusts_everyone_sees_the_whole_record():
    ev = weigh(LOG, A)
    assert (ev.kept, ev.broken) == (3, 1)
    assert ev.largest_repaid == 1000
    assert ev.reliability(1, 1) == pytest.approx(4 / 6)
    assert sorted(ev.repaid) == [((200, 1.0),), ((1000, 1.0),)]  # per counterparty, the 100 is redundant


def test_kept_promises_count_at_the_readers_credence_and_broken_ones_in_full():
    ev = weigh(LOG, A, trust={BANK: 1.0})  # the friend is unknown to this reader: no credence
    assert (ev.kept, ev.broken) == (2, 1)
    assert ev.repaid == (((200, 1.0),),)
    half = weigh(LOG, A, trust=trusting({BANK: 1.0}, default=0.5))
    assert (half.kept, half.broken) == (2.5, 1)
    assert weigh(LOG, A, trust=lambda who: 0.0).kept == 0
    assert weigh(LOG, A, trust=lambda who: 0.0).broken == 1  # a default counts whoever it was to
    assert weigh(LOG, A, trust=lambda who: 7.0).kept == 3  # credence is clipped to [0, 1]


def test_weights_fade_with_age_and_can_follow_the_fee():
    ev = weigh(LOG, A, retention=0.5, now=4)
    assert ev.kept == pytest.approx(0.5**3 + 0.5**2 + 0.5)
    assert ev.broken == 1
    assert weigh(LOG, A, retention=0.5).kept == ev.kept  # `now` defaults to the subject's latest entry
    fee = weigh(LOG, A, weight=by_fee(0.04))
    assert (fee.kept, fee.broken) == pytest.approx((13 / 0.04, 0.5 / 0.04))


def test_grouped_counterparties_are_one_piece_of_evidence():
    separate = weigh(LOG, A, trust=lambda who: 0.5)
    together = weigh(LOG, A, trust=lambda who: 0.5, group=lambda who: "one person")
    assert len(separate.repaid) == 2 and together.repaid == (((1000, 0.5),),)
    # Two independent half-trusted witnesses to 200 say more than one
    assert threshold_survival(200, separate.repaid, 10, 1.0) > threshold_survival(200, together.repaid, 10, 1.0)


def test_asset_filter_and_other_subjects():
    log = [Entry(A, BANK, 5, True, asset="x"), Entry(A, BANK, 7, True, asset="y")]
    assert weigh(log, A, asset="x").largest_repaid == 5
    assert weigh(LOG, OTHER).kept == weigh(LOG, OTHER).broken == 0
    assert weigh(LOG, OTHER).largest_repaid == 0


# --- the threshold belief ---

def test_no_record_gives_the_prior_and_full_trust_gives_the_ladder_formula():
    assert threshold_survival(50, (), 100, 1.0) == 1.0
    assert threshold_survival(400, (), 100, 1.0) == pytest.approx(0.25)
    assert threshold_survival(400, (), 100, 2.0) == pytest.approx(1 / 16)
    for due in (150, 300, 1000, 5000):
        for a in (0.5, 1.0, 2.0):
            assert repay_probability(due, (((300, 1.0),),), 10, a, shock_rate=0.02) == pytest.approx(
                ladder.repay_probability(due, 300, a, shock_rate=0.02))
    # A repayment nobody believes changes nothing
    assert threshold_survival(400, (((10_000, 0.0),),), 100, 1.0) == pytest.approx(0.25)


@pytest.mark.parametrize("repaid", [
    (((300.0, 0.6),),),
    (((300.0, 0.9),), ((800.0, 0.5),)),
    (((300.0, 0.9), (800.0, 0.2)),),  # one counterparty, two amounts: the larger is older and so less credible
    (((150.0, 1.0),), ((2000.0, 0.7),), ((2000.0, 0.7),)),
])
def test_threshold_survival_matches_monte_carlo(repaid):
    """
    Independent oracle: draw thresholds from the prior, and for each group decide which of its
    repayments were genuine (nested: the most credible ones first). Keep the draws that are
    consistent with every genuine repayment, and count how many reach each amount.
    """
    rng = np.random.default_rng(1)
    n, floor, a = 4_000_000, 100.0, 1.0
    c = floor * (1 - rng.random(n)) ** (-1 / a)
    consistent = np.ones(n, dtype=bool)
    for group in repaid:
        u = rng.random(n)
        for amount, credence in group:
            consistent &= ~((u < credence) & (c < amount))  # genuine, and they could not have repaid it
    survivors = c[consistent]
    for due in (120.0, 300.0, 500.0, 1000.0, 3000.0):
        assert (survivors >= due).mean() == pytest.approx(threshold_survival(due, repaid, floor, a), abs=0.003)


def test_largest_amount_due():
    kw = dict(risk_tolerance=0.10, floor=100, tail_index=1.0, shock_rate=0.02)
    k = ladder.screening_growth_factor(0.10, 1.0, 0.02)
    assert largest_amount_due((), **kw) == pytest.approx(100 * k)  # a stranger
    assert largest_amount_due((((5000, 1.0),),), **kw) == pytest.approx(5000 * k)  # a believed record
    assert largest_amount_due((((5000, 0.0),),), **kw) == pytest.approx(100 * k)  # a disbelieved one
    assert largest_amount_due((), risk_tolerance=0.01, floor=100, tail_index=1.0, shock_rate=0.02) == 0  # shocks alone exceed it
    # It is where the repayment probability meets the tolerance, and it rises with credence
    previous = 0
    for credence in (0.0, 0.5, 0.9, 0.99, 0.999, 1.0):
        repaid = (((5000, credence),),)
        x = largest_amount_due(repaid, **kw)
        assert repay_probability(x, repaid, 100, 1.0, 0.02) == pytest.approx(0.90, abs=1e-6)
        assert x >= previous
        previous = x


def test_an_extraordinary_record_needs_extraordinary_trust():
    """A repayment 100 times what a stranger is believed good for barely moves a reader who half believes it."""
    kw = dict(risk_tolerance=0.10, floor=100, tail_index=1.0, shock_rate=0.02)
    stranger = largest_amount_due((), **kw)
    assert largest_amount_due((((10_000, 0.5),),), **kw) < 1.01 * stranger
    assert largest_amount_due((((10_000, 0.99),),), **kw) < 1.2 * stranger
    assert largest_amount_due((((10_000, 0.999),),), **kw) > 5 * stranger


# --- the model keeps a log a reader can use ---

def test_the_model_logs_resolved_loans():
    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    for name in ("a", "bank", "friend"):
        e.add_agent(name, money=10_000)
    e.repay_loan(e.loan("a", "friend", 1000, 0))
    e.pay_dividend()
    e.repay_loan(e.loan("a", "bank", 100, 5))
    e.default_loan(e.loan("a", "bank", 200, 10))
    assert [(x.promisor, x.promisee, x.amount, x.kept, x.time) for x in e.log] == [
        ("a", "friend", 1000, True, 0), ("a", "bank", 105, True, 1), ("a", "bank", 210, False, 1)]
    assert e.log[0].fee_paid == pytest.approx(10)
    ev = weigh(e.log, "a", trust={"bank": 1.0}, weight=by_fee(0.04))
    assert (ev.kept, ev.broken) == pytest.approx((1.05 / 0.04, 2.1 / 0.04))
    assert ev.broken == pytest.approx(e.agents["a"].broken)  # the reader's broken counter is the chain's
