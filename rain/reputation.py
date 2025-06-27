# rain/reputation.py

"""
Core logic for the Rain Reputation Oracle.
Handles processing of on-chain events to determine reputation changes.
"""

from brownie import network # Required for network.chain.get_transaction if used directly here
from typing import List, Dict, Any

# Constants for reputation changes - these might be configurable in a more advanced setup
REP_GAIN_ON_FULFILLMENT = 25 * (10**18)  # Reward for keeping a promise
REP_LOSS_ON_DEFAULT = 100 * (10**18) # Penalty for breaking a promise

def process_promise_events(
    engine_contract: Any, # Brownie Contract object for CalculusEngine
    start_block: int,
    end_block: int
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Fetches and processes promise events from the CalculusEngine within a given block range.

    Args:
        engine_contract: The deployed CalculusEngine Brownie contract instance.
        start_block: The starting block number to scan for events.
        end_block: The ending block number to scan for events.

    Returns:
        A tuple containing two lists:
        - increases: A list of reputation increase objects.
        - decreases: A list of reputation decrease objects.
    """
    increases = []
    decreases = []

    print(f"  - [Core Logic] Scanning for events from block {start_block} to {end_block} in `rain.reputation`...")

    # Fetch events within the block range
    # Ensure events are fetched correctly using the passed contract instance
    fulfilled_events = engine_contract.events.get_sequence(
        event_type="PromiseFulfilled", from_block=start_block, to_block=end_block
    )
    defaulted_events = engine_contract.events.get_sequence(
        event_type="PromiseDefaulted", from_block=start_block, to_block=end_block
    )

    # Process fulfilled promises -> Reputation GAIN
    for event in fulfilled_events:
        promise_id = event.args.promiseId
        # Ensure promise_data is fetched using the passed contract instance
        promise_data = engine_contract.promises(promise_id)
        promisor = promise_data[1] # promisor is the 2nd element
        increases.append({"user": promisor, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{promise_id}"})
        print(f"    - [Core Logic] Found fulfilled promise {promise_id} by {promisor[:10]}...")

    # Process defaulted promises -> Reputation LOSS
    for event in defaulted_events:
        promise_id = event.args.promiseId
        promise_data = engine_contract.promises(promise_id)
        promisor = promise_data[1]
        decreases.append({"user": promisor, "amount": REP_LOSS_ON_DEFAULT, "reason": f"PROMISE_DEFAULTED:{promise_id}"})
        print(f"    - [Core Logic] Found defaulted promise {promise_id} by {promisor[:10]}...")

    return increases, decreases

# Placeholder for other reputation-related off-chain logic if needed
