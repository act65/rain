import pytest
from unittest.mock import MagicMock, PropertyMock

from rain.reputation import (
    process_promise_events,
    REP_GAIN_ON_FULFILLMENT,
    REP_LOSS_ON_DEFAULT
)

# --- Mock Event and Contract Objects ---

class MockEvent:
    def __init__(self, event_type: str, promise_id: int, block_number: int):
        self.event = event_type # Brownie events have an 'event' attribute for type
        self.args = PropertyMock() # Using PropertyMock for args

        # Dynamically set attributes on the PropertyMock instance
        # In Brownie, event.args is like a dictionary or an object with attributes
        # For this mock, we'll make it an object with a promiseId attribute
        class Args:
            pass

        mock_args_instance = Args()
        mock_args_instance.promiseId = promise_id

        # Configure the PropertyMock to return our mock_args_instance
        # This requires careful handling if args is accessed multiple times or expected to be a dict
        # For simple attribute access like event.args.promiseId, this should work.
        # A more robust way might be to make self.args a MagicMock itself.
        # Let's try with a simple object first.
        self.args = mock_args_instance
        self.block_number = block_number # For completeness, though not directly used by func

class MockCalculusEngineContract:
    def __init__(self, events_map=None, promises_map=None):
        # events_map: dict mapping event_type to a list of MockEvent objects
        self.events_map = events_map if events_map else {}
        # promises_map: dict mapping promise_id to promise_data tuple (idx 1 is promisor)
        self.promises_map = promises_map if promises_map else {}

        # Mock the 'events' attribute which has a 'get_sequence' method
        self.events = MagicMock()

        def mock_get_sequence(event_type, from_block, to_block):
            # Filter events by block range conceptually (actual filtering is by Brownie)
            # For the mock, we assume events provided are within the intended range
            # if the test sets them up that way.
            return self.events_map.get(event_type, [])

        self.events.get_sequence = MagicMock(side_effect=mock_get_sequence)

    def promises(self, promise_id: int):
        if promise_id in self.promises_map:
            return self.promises_map[promise_id]
        # Default or raise error if promise_id not found, depends on expected contract behavior
        # For tests, ensure all accessed promise_ids are in promises_map
        raise ValueError(f"MockCalculusEngine: Promise ID {promise_id} not found in promises_map.")

# --- Test Addresses ---
USER_A = "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
USER_B = "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

# --- Test Cases ---

def test_process_no_events():
    mock_engine = MockCalculusEngineContract()
    increases, decreases = process_promise_events(mock_engine, 1, 100)
    assert increases == []
    assert decreases == []

def test_process_only_fulfilled_events():
    promise_id_1 = 101
    promise_id_2 = 102

    events_fulfilled = [
        MockEvent("PromiseFulfilled", promise_id_1, 50),
        MockEvent("PromiseFulfilled", promise_id_2, 60),
    ]
    promises_data = {
        promise_id_1: (0, USER_A, 0, 0, 0, 0, 0), # promisor at index 1
        promise_id_2: (0, USER_B, 0, 0, 0, 0, 0),
    }
    mock_engine = MockCalculusEngineContract(
        events_map={"PromiseFulfilled": events_fulfilled},
        promises_map=promises_data
    )

    increases, decreases = process_promise_events(mock_engine, 1, 100)

    assert len(increases) == 2
    assert decreases == []

    assert {"user": USER_A, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{promise_id_1}"} in increases
    assert {"user": USER_B, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{promise_id_2}"} in increases

def test_process_only_defaulted_events():
    promise_id_3 = 201
    promise_id_4 = 202

    events_defaulted = [
        MockEvent("PromiseDefaulted", promise_id_3, 70),
        MockEvent("PromiseDefaulted", promise_id_4, 80),
    ]
    promises_data = {
        promise_id_3: (0, USER_A, 0, 0, 0, 0, 0),
        promise_id_4: (0, USER_B, 0, 0, 0, 0, 0),
    }
    mock_engine = MockCalculusEngineContract(
        events_map={"PromiseDefaulted": events_defaulted},
        promises_map=promises_data
    )

    increases, decreases = process_promise_events(mock_engine, 1, 100)

    assert increases == []
    assert len(decreases) == 2

    assert {"user": USER_A, "amount": REP_LOSS_ON_DEFAULT, "reason": f"PROMISE_DEFAULTED:{promise_id_3}"} in decreases
    assert {"user": USER_B, "amount": REP_LOSS_ON_DEFAULT, "reason": f"PROMISE_DEFAULTED:{promise_id_4}"} in decreases

def test_process_mixed_events():
    pid_f1 = 301 # Fulfilled by A
    pid_d1 = 302 # Defaulted by B
    pid_f2 = 303 # Fulfilled by B

    events_fulfilled = [MockEvent("PromiseFulfilled", pid_f1, 50), MockEvent("PromiseFulfilled", pid_f2, 70)]
    events_defaulted = [MockEvent("PromiseDefaulted", pid_d1, 60)]

    promises_data = {
        pid_f1: (0, USER_A, 0, 0, 0, 0, 0),
        pid_d1: (0, USER_B, 0, 0, 0, 0, 0),
        pid_f2: (0, USER_B, 0, 0, 0, 0, 0),
    }
    mock_engine = MockCalculusEngineContract(
        events_map={
            "PromiseFulfilled": events_fulfilled,
            "PromiseDefaulted": events_defaulted
        },
        promises_map=promises_data
    )

    increases, decreases = process_promise_events(mock_engine, 1, 100)

    assert len(increases) == 2
    assert {"user": USER_A, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{pid_f1}"} in increases
    assert {"user": USER_B, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{pid_f2}"} in increases

    assert len(decreases) == 1
    assert {"user": USER_B, "amount": REP_LOSS_ON_DEFAULT, "reason": f"PROMISE_DEFAULTED:{pid_d1}"} in decreases

def test_process_events_promise_data_not_found_gracefully_fails_or_as_expected():
    # This test depends on how the actual contract call engine_contract.promises(promise_id)
    # would behave if a promise_id from an event log does not exist (e.g., due to reorg or bad data).
    # The current mock raises ValueError. If the real contract reverts or returns default/zero data,
    # the test and potentially the main code might need adjustment.
    # For now, we test that if mock_engine.promises raises, process_promise_events also raises.
    pid_f_bad = 401
    events_fulfilled = [MockEvent("PromiseFulfilled", pid_f_bad, 50)]

    # promises_map does NOT contain pid_f_bad
    mock_engine = MockCalculusEngineContract(events_map={"PromiseFulfilled": events_fulfilled})

    with pytest.raises(ValueError, match=f"MockCalculusEngine: Promise ID {pid_f_bad} not found in promises_map."):
        process_promise_events(mock_engine, 1, 100)

# Note: The mock for event.args.promiseId was simplified.
# A real Brownie event args object is more complex (AttributeDict).
# If event.args were used in more ways (e.g., event.args['promiseId'] or iterating over args),
# the MockEvent.args would need to be a MagicMock configured to behave like AttributeDict.
# For current usage (event.args.promiseId), the simple object in MockEvent should suffice.
