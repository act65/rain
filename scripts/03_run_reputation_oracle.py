# File: 03_run_reputation_oracle.py (General-Purpose & Stateful)

from brownie import (
    accounts,
    network,
    CalculusEngine,
    RainReputation,
    ReputationUpdater,
)
import json
import time

# --- ORACLE CONFIGURATION ---
DEPLOYMENT_FILE = "deployment_addresses.json"
ORACLE_STATE_FILE = "oracle_state.json" # To store the last block we processed
# In a real environment, you'd use a more robust key management solution
ORACLE_OPERATOR = accounts[0] 

# Process blocks in batches to be safe against re-orgs and RPC limits
BLOCK_BATCH_SIZE = 1000 
# How many blocks to wait for confirmation before processing
BLOCK_CONFIRMATIONS = 5 

# The "Rules Engine" parameters for the oracle
REP_GAIN_ON_FULFILLMENT = 25 * (10**18)  # Reward for keeping a promise
REP_LOSS_ON_DEFAULT = 100 * (10**18) # Penalty for breaking a promise


def load_state():
    """Loads the last processed block number from the state file."""
    try:
        with open(ORACLE_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # If the file doesn't exist, we start from the block the engine was deployed
        with open(DEPLOYMENT_FILE) as f:
            addresses = json.load(f)
        engine_deployment_tx_hash = CalculusEngine.at(addresses["CalculusEngine"]).tx.txid
        engine_deployment_block = network.chain.get_transaction(engine_deployment_tx_hash).block_number
        return {"last_processed_block": engine_deployment_block}

def save_state(state):
    """Saves the last processed block number to the state file."""
    with open(ORACLE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def process_events(engine, start_block, end_block):
    """Fetches and processes promise events within a given block range."""
    increases = []
    decreases = []

    print(f"  - Scanning for events from block {start_block} to {end_block}...")

    # Fetch events within the block range
    fulfilled_events = engine.events.get_sequence(
        event_type="PromiseFulfilled", from_block=start_block, to_block=end_block
    )
    defaulted_events = engine.events.get_sequence(
        event_type="PromiseDefaulted", from_block=start_block, to_block=end_block
    )

    # Process fulfilled promises -> Reputation GAIN
    for event in fulfilled_events:
        promise_id = event.args.promiseId
        promise_data = engine.promises(promise_id)
        promisor = promise_data[1] # promisor is the 2nd element
        increases.append({"user": promisor, "amount": REP_GAIN_ON_FULFILLMENT, "reason": f"PROMISE_FULFILLED:{promise_id}"})
        print(f"    - Found fulfilled promise {promise_id} by {promisor[:10]}...")

    # Process defaulted promises -> Reputation LOSS
    for event in defaulted_events:
        promise_id = event.args.promiseId
        promise_data = engine.promises(promise_id)
        promisor = promise_data[1]
        decreases.append({"user": promisor, "amount": REP_LOSS_ON_DEFAULT, "reason": f"PROMISE_DEFAULTED:{promise_id}"})
        print(f"    - Found defaulted promise {promise_id} by {promisor[:10]}...")
        
    return increases, decreases

def main():
    """
    Main oracle loop. This script is designed to be run repeatedly.
    It fetches new events since its last run, processes them, and commits
    reputation changes to the chain.
    """
    print("--- REPUTATION ORACLE SERVICE ---")

    # --- 1. SETUP ---
    state = load_state()
    last_processed_block = state["last_processed_block"]
    
    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

    calculus_engine = CalculusEngine.at(addresses["CalculusEngine"])
    reputation_updater = ReputationUpdater.at(addresses["ReputationUpdater"])
    rain_reputation = RainReputation.at(addresses["RainReputation"]) # For verification

    current_block = network.chain.height
    # We leave a buffer for chain confirmations
    target_block = current_block - BLOCK_CONFIRMATIONS

    print(f"Last processed block: {last_processed_block}")
    print(f"Current chain height: {current_block}")

    if last_processed_block >= target_block:
        print("\nNo new blocks to process. Exiting.")
        return

    # --- 2. PROCESS IN BATCHES ---
    all_increases = []
    all_decreases = []

    for start in range(last_processed_block + 1, target_block + 1, BLOCK_BATCH_SIZE):
        end = min(start + BLOCK_BATCH_SIZE - 1, target_block)
        increases, decreases = process_events(calculus_engine, start, end)
        all_increases.extend(increases)
        all_decreases.extend(decreases)

    # --- 3. COMMIT CHANGES ON-CHAIN ---
    if not all_increases and not all_decreases:
        print("\nNo new promise resolutions found in the processed blocks.")
    else:
        print("\nFound new events. Committing reputation changes on-chain...")
        try:
            tx = reputation_updater.applyReputationChanges(all_increases, all_decreases, {"from": ORACLE_OPERATOR})
            print(f"  - Success! Transaction hash: {tx.txid}")
        except Exception as e:
            print(f"  - ERROR: Failed to commit changes: {e}")
            return # Do not update state if commit fails

    # --- 4. UPDATE STATE ---
    state["last_processed_block"] = target_block
    save_state(state)
    print(f"\nSuccessfully processed up to block {target_block}. State updated.")

    # --- 5. (Optional) VERIFY A KNOWN ACTOR'S SCORE ---
    # This part is for demonstration during simulation.
    # In production, you'd rely on logs and monitoring.
    print("\n--- Verifying Scores (for simulation context) ---")
    try:
        bob = accounts[2]
        charlie = accounts[3]
        print(f"  - Bob's Final Reputation: {rain_reputation.reputationScores(bob) / 10**18}")
        print(f"  - Charlie's Final Reputation: {rain_reputation.reputationScores(charlie) / 10**18}")
    except Exception:
        print("  - Could not verify simulation accounts (this is normal if not in a test environment).")