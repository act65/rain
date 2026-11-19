# File: scripts/run_reputation_oracle.py
"""
The reputation oracle. Designed to be run repeatedly: each run reads the promise
events emitted since the previous run, applies the rules in `rain.reputation`, and
commits the resulting reputation changes through the ReputationUpdater.
"""

import json

from ape import accounts, chain, networks, project

from rain.reputation import process_promise_log, to_update_tuples
from rain.utils import load_deployment_data

DEPLOYMENT_FILE = "deployment_addresses.json"
ORACLE_STATE_FILE = "oracle_state.json"  # Remembers the last block we processed

# Process blocks in batches to stay within RPC limits
BLOCK_BATCH_SIZE = 1000
# How many blocks to wait before treating a block as final. A local development
# chain never re-orgs, and waiting there would leave the latest events unprocessed.
LIVE_BLOCK_CONFIRMATIONS = 5


def block_confirmations():
    return 0 if networks.provider.network.is_local else LIVE_BLOCK_CONFIRMATIONS


def load_state(engine_address):
    """
    Loads the last processed block. The state is only valid for the CalculusEngine
    it was recorded against: after a redeploy (or a fresh local chain) we start again.
    """
    try:
        with open(ORACLE_STATE_FILE, "r") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    if state.get("calculus_engine") != engine_address or state.get("last_processed_block", 0) > chain.blocks.height:
        print("No oracle state for this deployment. Scanning from the first block.")
        state = {"calculus_engine": engine_address, "last_processed_block": -1}
    return state


def save_state(state):
    with open(ORACLE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def main():
    print("--- REPUTATION ORACLE SERVICE ---")
    oracle_operator = accounts.test_accounts[0]  # Must hold UPDATER_ROLE on the ReputationUpdater

    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        raise RuntimeError("Could not load deployment addresses. Run scripts/deploy.py first.")

    calculus_engine = project.CalculusEngine.at(addresses["CalculusEngine"])
    reputation_updater = project.ReputationUpdater.at(addresses["ReputationUpdater"])
    rain_reputation = project.RainReputation.at(addresses["RainReputation"])

    state = load_state(calculus_engine.address)
    last_processed_block = state["last_processed_block"]
    target_block = chain.blocks.height - block_confirmations()

    print(f"Last processed block: {last_processed_block}")
    print(f"Target block: {target_block}")
    if last_processed_block >= target_block:
        print("\nNo new blocks to process. Exiting.")
        return

    # --- 1. READ THE PROMISE LOG ---
    increases, decreases = [], []
    for start in range(last_processed_block + 1, target_block + 1, BLOCK_BATCH_SIZE):
        end = min(start + BLOCK_BATCH_SIZE - 1, target_block)
        batch_increases, batch_decreases, withheld = process_promise_log(calculus_engine, rain_reputation, start, end)
        increases.extend(batch_increases)
        decreases.extend(batch_decreases)
        # A promise kept while its promisor was delinquent earns nothing.
        for change in withheld:
            print(f"  - {change['reason']} earns nothing: {change['user']} was delinquent when it was kept.")

    # --- 2. COMMIT CHANGES ON-CHAIN ---
    if not increases and not decreases:
        print("\nNo reputation changes to commit.")
    else:
        print(f"\nCommitting {len(increases)} increase(s) and {len(decreases)} decrease(s)...")
        for change in increases + decreases:
            print(f"  - {change['reason']}: {change['user']}")
        tx = reputation_updater.applyReputationChanges(
            to_update_tuples(increases), to_update_tuples(decreases), sender=oracle_operator
        )
        print(f"  - Success! Transaction hash: {tx.txn_hash}")

    # --- 3. UPDATE STATE (only reached if the commit succeeded) ---
    state["last_processed_block"] = target_block
    save_state(state)
    print(f"\nProcessed up to block {target_block}. State updated.")
    return increases, decreases
