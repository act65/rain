# File: 03_run_reputation_oracle.py (General-Purpose & Stateful)

from brownie import (
    accounts,
    network,
    CalculusEngine,
    RainReputation,
    ReputationUpdater,
)
from rain.utils import load_deployment_data
from rain.reputation import process_promise_events, REP_GAIN_ON_FULFILLMENT, REP_LOSS_ON_DEFAULT # Updated import
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

# REP_GAIN_ON_FULFILLMENT and REP_LOSS_ON_DEFAULT are now imported from rain.reputation

def load_state():
    """Loads the last processed block number from the state file."""
    try:
        with open(ORACLE_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # If the file doesn't exist, we start from the block the engine was deployed
        addresses = load_deployment_data(DEPLOYMENT_FILE)
        if not addresses or "CalculusEngine" not in addresses:
            print("Error: Could not load CalculusEngine address for initial state. Exiting oracle.")
            # In a real scenario, might raise an exception or handle differently
            return {"last_processed_block": network.chain.height - BLOCK_CONFIRMATIONS -1} # Fallback

        engine_contract_address = addresses["CalculusEngine"]
        # Ensure the contract is deployed and accessible before getting tx details
        try:
            engine_contract = CalculusEngine.at(engine_contract_address)
            engine_deployment_tx_hash = engine_contract.tx.txid
            engine_deployment_block = network.chain.get_transaction(engine_deployment_tx_hash).block_number
            print(f"Oracle state file not found. Initializing from CalculusEngine deployment block: {engine_deployment_block}")
            return {"last_processed_block": engine_deployment_block}
        except Exception as e:
            print(f"Error accessing CalculusEngine deployment info: {e}. Defaulting last processed block.")
            # Fallback if contract or tx info isn't available (e.g., not yet run on this network)
            return {"last_processed_block": network.chain.height - BLOCK_CONFIRMATIONS -1 if network.chain.height > BLOCK_CONFIRMATIONS else 0}

def save_state(state):
    """Saves the last processed block number to the state file."""
    with open(ORACLE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

# The process_events function has been moved to rain.reputation.py
# It is now imported as process_promise_events.

def main():
    """
    Main oracle loop. This script is designed to be run repeatedly.
    It fetches new events since its last run, processes them, and commits
    reputation changes to the chain.
    """
    print("--- REPUTATION ORACLE SERVICE ---")

    # --- 1. SETUP ---
    state = load_state()
    last_processed_block = state.get("last_processed_block", 0) # Use .get for safety
    
    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        print("Failed to load deployment addresses for oracle. Exiting.")
        return

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
        # Use the imported function from rain.reputation
        increases, decreases = process_promise_events(calculus_engine, start, end)
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