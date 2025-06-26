# File: scripts/05_run_set_protocol_fee.py

from brownie import (
    accounts,
    Contract,
    CalculusEngine,
    RainReputation,
    TreasuryV2,
)
import json
import math

# --- KEEPER CONFIGURATION ---
DEPLOYMENT_FILE = "deployment_addresses.json"
KEEPER_ACCOUNT = accounts[0]  # This account must have ADMIN role on CalculusEngine

# This value MUST match the one in the reputation oracle script
REP_GAIN_ON_FULFILLMENT = 25 * (10**18)

# We want the fee to be 1.5x the value of the reputation gain to create a buffer
# and make farming unprofitable.
SAFETY_MARGIN = 1.5


def main():
    """
    A keeper script that dynamically adjusts the protocol fee based on the
    economic value of reputation, derived from the last dividend payout.
    """
    print("--- DYNAMIC PROTOCOL FEE KEEPER ---")

    # --- 1. SETUP ---
    print("\nLoading contracts and fetching initial state...")
    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

    # Instantiate contract objects from addresses
    # Using Contract.at() is a robust way to interact with already deployed contracts
    calculus_engine = Contract.from_abi("CalculusEngine", addresses["CalculusEngine"], CalculusEngine.abi)
    rain_reputation = Contract.from_abi("RainReputation", addresses["RainReputation"], RainReputation.abi)
    treasury_v2 = Contract.from_abi("TreasuryV2", addresses["TreasuryV2"], TreasuryV2.abi)

    current_fee = calculus_engine.protocolFee()
    print(f"  - Current Protocol Fee: {current_fee / 10**18} DMD")

    # --- 2. FETCH DATA FROM PROTOCOL ---
    print("\nFetching data for fee calculation...")
    
    # Get the total amount of reputation in the system
    total_reputation = rain_reputation.totalReputation()
    if total_reputation == 0:
        print("  - ERROR: Total reputation is zero. Cannot calculate fee. Exiting.")
        return
    print(f"  - Total System Reputation: {total_reputation / 10**18}")

    # Get the details of the last dividend cycle
    num_cycles = treasury_v2.getNumberOfCycles()
    if num_cycles == 0:
        print("  - WARNING: No dividend cycles have occurred yet. Cannot calculate new fee. Exiting.")
        return
    
    # We use the most recently completed cycle to determine value
    last_cycle_id = num_cycles - 1
    last_cycle_details = treasury_v2.getCycleDetails(last_cycle_id)
    last_dividend_amount = last_cycle_details[2] # totalAmount is the 3rd element
    
    if last_dividend_amount == 0:
        print("  - WARNING: Last dividend amount was zero. Cannot calculate fee. Exiting.")
        return
    print(f"  - Last Dividend Pool Size: {last_dividend_amount / 10**18} DMD")

    # --- 3. CALCULATE NEW FEE ---
    print("\nCalculating new protocol fee...")
    
    # Value per Rep = Last Dividend Amount / Total Reputation
    # This gives us a proxy for the cash-flow value of a single point of reputation
    value_per_rep = last_dividend_amount / total_reputation
    print(f"  - Calculated Value Per Reputation Point: {value_per_rep}")

    # Value of Rep Gain = Value per Rep * Amount of Rep Gained for a Fulfilled Promise
    value_of_rep_gain = value_per_rep * REP_GAIN_ON_FULFILLMENT
    print(f"  - Economic Value of Reputation Gain from one action: {value_of_rep_gain / 10**18} DMD")

    # New Fee = Value of Rep Gain * Safety Margin
    # We use math.ceil to ensure we always round up, maintaining the inequality.
    new_protocol_fee = math.ceil(value_of_rep_gain * SAFETY_MARGIN)
    print(f"  - Calculated New Fee (with {SAFETY_MARGIN}x margin): {new_protocol_fee / 10**18} DMD")

    # --- 4. EXECUTE ON-CHAIN ---
    if new_protocol_fee == current_fee:
        print("\nNew fee is the same as the current fee. No update needed.")
    else:
        print("\nNew fee is different. Submitting update transaction...")
        try:
            tx = calculus_engine.setProtocolFee(new_protocol_fee, {"from": KEEPER_ACCOUNT})
            tx.wait(1)
            print(f"  - Success! Protocol fee updated in transaction: {tx.txid}")
            print(f"  - New on-chain fee: {calculus_engine.protocolFee() / 10**18} DMD")
        except Exception as e:
            print(f"  - ERROR: Transaction failed: {e}")

    print("\nKeeper run complete.")