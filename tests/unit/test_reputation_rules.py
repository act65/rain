"""
Claims tested: a kept promise earns its promisor reputation in proportion to the fee paid, at
the point price; a broken promise is recorded with the same weight, and takes no reputation;
each resolved promise yields at most one change; delinquent users are separated out.
"""
from types import SimpleNamespace

import pytest

from rain.reputation import (
    POINT,
    delinquency_timeline,
    process_promise_events,
    process_promise_log,
    reputation_changes,
    reward,
    to_update_tuples,
    was_delinquent,
)

A, B, C = "0xA", "0xB", "0xC"
PRICE = POINT // 25  # 0.04 currency units per point
FEE = POINT  # a fee of 1 currency unit earns 25 points
REWARD = 25 * POINT


@pytest.mark.parametrize("fee,price,expected", [
    (POINT, POINT // 25, 25 * POINT),       # 1 unit of fee at 0.04 per point
    (POINT // 10, POINT // 25, 25 * POINT // 10),
    (0, POINT // 25, 0),
    (7, 3, 7 * POINT // 3),                  # rounded down
    (POINT, POINT, POINT),
])
def test_reward_is_fee_over_point_price(fee, price, expected):
    assert reward(fee, price) == expected


def test_reward_is_linear_in_the_fee():
    assert reward(10 * FEE, PRICE) == 10 * reward(FEE, PRICE)


def test_reward_rejects_bad_inputs():
    with pytest.raises(ValueError):
        reward(1, 0)
    with pytest.raises(ValueError):
        reward(-1, PRICE)


def test_reputation_changes():
    increases, broken = reputation_changes([(1, A, FEE), (2, B, 4 * FEE)], [(3, A, 2 * FEE)], PRICE)
    assert increases == [
        {"user": A, "amount": REWARD, "reason": "PROMISE_FULFILLED:1"},
        {"user": B, "amount": 4 * REWARD, "reason": "PROMISE_FULFILLED:2"},
    ]
    assert broken == [{"user": A, "amount": 2 * REWARD, "reason": "PROMISE_DEFAULTED:3"}]


def test_reputation_changes_empty():
    assert reputation_changes([], [], PRICE) == ([], [])


def test_a_kept_promise_that_paid_no_fee_earns_nothing():
    increases, _ = reputation_changes([(1, A, 0), (2, B, FEE)], [], PRICE)
    assert [c["user"] for c in increases] == [B]


def test_a_broken_promise_weighs_what_it_would_have_earned():
    """Kept or broken, a promise is one observation of the same weight: the two counters share a unit."""
    for fee in (FEE, 50 * FEE, 7):
        kept, _ = reputation_changes([(1, A, fee)], [], PRICE)
        _, broken = reputation_changes([], [(1, A, fee)], PRICE)
        assert broken[0]["amount"] == kept[0]["amount"] == reward(fee, PRICE)
    assert reputation_changes([], [(1, A, 0)], PRICE) == ([], [])  # no fee, no weight


def test_one_change_per_promise_even_for_the_same_user():
    increases, _ = reputation_changes([(1, A, FEE), (2, A, FEE), (3, A, FEE)], [], PRICE)
    assert [c["reason"] for c in increases] == [f"PROMISE_FULFILLED:{i}" for i in (1, 2, 3)]


def test_to_update_tuples():
    increases, _ = reputation_changes([(1, A, FEE)], [], PRICE)
    assert to_update_tuples(increases) == [(A, REWARD, "PROMISE_FULFILLED:1")]


class FakeEvent:
    """Mimics an Ape contract event: `.range(start, stop)` yields the logs in [start, stop)."""

    def __init__(self, logs):
        self._logs = logs  # (arguments, block, log_index)

    def range(self, start, stop):
        return iter(
            SimpleNamespace(event_arguments=arguments, block_number=block, log_index=idx)
            for (arguments, block, idx) in self._logs
            if start <= block < stop
        )


class FakeReputation:
    """Mimics the reputation contract's log of delinquency changes: (user, is_delinquent, block, log_index)."""

    def __init__(self, changes=()):
        self.DelinquentStatusChanged = FakeEvent(
            [({"user": user, "isDelinquent": status}, block, idx) for (user, status, block, idx) in changes])


class FakeEngine:
    """Mimics the parts of the CalculusEngine contract object that the oracle reads."""

    def __init__(self, promisors, events, fees=None, point_price=PRICE):
        self._promisors = promisors
        self._fees = fees or {}
        self._point_price = point_price
        for kind in ("PromiseFulfilled", "PromiseDefaulted"):
            setattr(self, kind, FakeEvent([({"promiseId": pid}, block, idx) for (k, pid, block, idx) in events if k == kind]))

    def promises(self, promise_id):
        # (actionId, promisor, promisee, asset, amount, deadline, status, feePaid)
        return (0, self._promisors[promise_id], "0x0", "0x0", 0, 0, 0, self._fees.get(promise_id, FEE))

    def pointPrice(self):
        return self._point_price


def test_process_promise_events_respects_block_range_and_chain_order():
    engine = FakeEngine(
        promisors={1: A, 2: B, 3: C, 4: A},
        events=[
            ("PromiseFulfilled", 2, 12, 0),
            ("PromiseFulfilled", 1, 10, 3),
            ("PromiseDefaulted", 3, 11, 0),
            ("PromiseFulfilled", 4, 20, 0),  # outside the range
        ],
    )
    increases, decreases = process_promise_events(engine, 10, 15)
    assert [(c["user"], c["reason"]) for c in increases] == [
        (A, "PROMISE_FULFILLED:1"),
        (B, "PROMISE_FULFILLED:2"),
    ]
    assert [(c["user"], c["reason"]) for c in decreases] == [(C, "PROMISE_DEFAULTED:3")]


def test_process_promise_events_rewards_by_fee_paid_at_the_engines_point_price():
    engine = FakeEngine({1: A, 2: B}, [("PromiseFulfilled", 1, 5, 0), ("PromiseFulfilled", 2, 5, 1)],
                        fees={1: FEE, 2: 3 * FEE}, point_price=2 * PRICE)
    increases, _ = process_promise_events(engine, 0, 10)
    assert [c["amount"] for c in increases] == [REWARD // 2, 3 * REWARD // 2]


def test_adjacent_block_ranges_cover_every_event_exactly_once():
    events = [("PromiseFulfilled", i, block, 0) for i, block in enumerate(range(1, 21), start=1)]
    engine = FakeEngine({i: A for i in range(1, 21)}, events)
    seen = []
    for start in range(0, 21, 7):
        increases, _ = process_promise_events(engine, start, min(start + 6, 20))
        seen += [c["reason"] for c in increases]
    assert seen == [f"PROMISE_FULFILLED:{i}" for i in range(1, 21)]


# --- Delinquency: status is read as of the promise's own position in the log ---

def test_was_delinquent_follows_the_timeline():
    timeline = {A: [(10, 0, True), (20, 5, False), (30, 0, True)]}
    assert not was_delinquent(timeline, A, 9, 99)
    assert not was_delinquent(timeline, A, 10, 0)  # the change itself comes first; "just before" it they were not
    assert was_delinquent(timeline, A, 10, 1)
    assert was_delinquent(timeline, A, 20, 5)
    assert not was_delinquent(timeline, A, 20, 6)
    assert was_delinquent(timeline, A, 31, 0)
    assert not was_delinquent(timeline, B, 31, 0)  # never flagged


def test_delinquency_timeline_is_built_in_chain_order_up_to_the_block():
    rep = FakeReputation([(A, False, 20, 5), (A, True, 10, 0), (B, True, 15, 0), (A, True, 30, 0)])
    assert delinquency_timeline(rep, 20) == {A: [(10, 0, True), (20, 5, False)], B: [(15, 0, True)]}


def test_promise_kept_while_delinquent_earns_nothing():
    engine = FakeEngine({1: A, 2: A, 3: A, 4: B}, [
        ("PromiseFulfilled", 1, 5, 0),   # before A's default: earns
        ("PromiseFulfilled", 2, 12, 0),  # while A is delinquent: earns nothing
        ("PromiseFulfilled", 3, 25, 0),  # after A settled: earns
        ("PromiseFulfilled", 4, 12, 1),  # B was never delinquent
    ])
    rep = FakeReputation([(A, True, 10, 0), (A, False, 20, 0)])
    increases, decreases, withheld = process_promise_log(engine, rep, 0, 30)
    assert [c["reason"] for c in increases] == ["PROMISE_FULFILLED:1", "PROMISE_FULFILLED:4", "PROMISE_FULFILLED:3"]
    assert [(c["user"], c["reason"], c["amount"]) for c in withheld] == [(A, "PROMISE_FULFILLED:2", REWARD)]
    assert decreases == []


def test_the_result_does_not_depend_on_when_the_oracle_runs():
    """Processing the log in one pass at the end, or block by block as it grows, gives the same rewards."""
    promises = {1: A, 2: A, 3: B}
    events = [("PromiseFulfilled", 1, 5, 0), ("PromiseDefaulted", 3, 8, 0), ("PromiseFulfilled", 2, 12, 0)]
    rep = FakeReputation([(A, True, 10, 0)])  # A keeps promise 1, then becomes delinquent, then keeps promise 2
    engine = FakeEngine(promises, events)

    late = process_promise_log(engine, rep, 0, 20)
    prompt = ([], [], [])
    for block in range(0, 21):
        for collected, new in zip(prompt, process_promise_log(engine, rep, block, block)):
            collected.extend(new)
    assert prompt == late
    assert [c["reason"] for c in late[0]] == ["PROMISE_FULFILLED:1"]  # earned, although A is delinquent by the end
    assert [c["reason"] for c in late[2]] == ["PROMISE_FULFILLED:2"]
