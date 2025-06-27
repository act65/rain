# File: scripts/05_run_set_protocol_fee.py

from brownie import (
    accounts,
    Contract,
    CalculusEngine,
    RainReputation,
    TreasuryV2,
)
from rain.utils import load_deployment_data
from rain.protocol_fee import calculate_new_protocol_fee, DEFAULT_REP_GAIN_ON_FULFILLMENT, DEFAULT_SAFETY_MARGIN # Updated import
import math # math might still be used by the script, or by the lib

# --- KEEPER CONFIGURATION ---
DEPLOYMENT_FILE = "deployment_addresses.json"
KEEPER_ACCOUNT = accounts[0]  # This account must have ADMIN role on CalculusEngine

# Configuration for fee calculation, can be overridden if needed by passing to calculate_new_protocol_fee
# Using defaults from rain.protocol_fee for consistency.
REP_GAIN_ON_FULFILLMENT = DEFAULT_REP_GAIN_ON_FULFILLMENT
SAFETY_MARGIN = DEFAULT_SAFETY_MARGIN


def main():
    """
    A keeper script that dynamically adjusts the protocol fee based on the
    economic value of reputation, derived from the last dividend payout.
    """
    print("--- DYNAMIC PROTOCOL FEE KEEPER ---")

    # --- 1. SETUP ---
    print("\nLoading contracts and fetching initial state...")
    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        print("Failed to load deployment addresses for protocol fee keeper. Exiting.")
        return

    # Instantiate contract objects from addresses
    # Using Contract.at() is a robust way to interact with already deployed contracts
    calculus_engine = Contract.from_abi("CalculusEngine", addresses["CalculusEngine"], CalculusEngine.abi)
    rain_reputation = Contract.from_abi("RainReputation", addresses["RainReputation"], RainReputation.abi)
    treasury_v2 = Contract.from_abi("TreasuryV2", addresses["TreasuryV2"], TreasuryV2.abi)

    current_fee = calculus_engine.protocolFee()
    print(f"  - Script: Current On-Chain Protocol Fee: {current_fee / 10**18} DMD")

    # --- 2. CALCULATE NEW FEE USING LIBRARY FUNCTION ---
    print("\nCalculating new protocol fee using rain.protocol_fee...")
    new_protocol_fee = calculate_new_protocol_fee(
        calculus_engine, # Pass the contract instance
        rain_reputation, # Pass the contract instance
        treasury_v2,     # Pass the contract instance
        rep_gain_on_fulfillment=REP_GAIN_ON_FULFILLMENT, # Pass configured value
        safety_margin=SAFETY_MARGIN # Pass configured value
    )

    if new_protocol_fee is None:
        print("  - Script: Fee calculation returned None. Exiting without update.")
        return

    print(f"  - Script: Proposed New Fee from library: {new_protocol_fee / 10**18} DMD")

    # --- 3. EXECUTE ON-CHAIN ---
    if new_protocol_fee == current_fee:
        print("\nScript: New fee is the same as the current fee. No update needed.")
    else:
        print("\nScript: New fee is different. Submitting update transaction...")
        try:
            tx = calculus_engine.setProtocolFee(int(new_protocol_fee), {"from": KEEPER_ACCOUNT}) # Ensure it's int
            tx.wait(1)
            print(f"  - Success! Protocol fee updated in transaction: {tx.txid}")
            print(f"  - New on-chain fee: {calculus_engine.protocolFee() / 10**18} DMD")
        except Exception as e:
            print(f"  - ERROR: Transaction failed: {e}")

    print("\nKeeper run complete.")