# File: 04_run_dividend_distribution.py (Corrected for TreasuryV2)

from brownie import (
    accounts,
    network,
    Contract,
    CurrencyToken,
    RainReputation,
    TreasuryV2,
    web3, # web3 is still needed for direct use if any, but also used by rain.dividends
)
# MerkleTree will be used by rain.dividends
from rain.utils import load_deployment_data
from rain.dividends import calculate_dividend_shares, get_merkle_proof # Updated import
import json

# --- CONFIGURATION ---
DEPLOYMENT_FILE = "deployment_addresses.json"
# The amount of fees we will simulate having been collected by the Treasury
CAPITAL_TO_INVEST = 500_000 * (10**18) 

# --- MOCK YIELD SOURCE CONTRACT ---
# We will deploy a simple mock contract to simulate an external protocol like Aave.
MOCK_YIELD_SOURCE_CODE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
contract MockYieldSource {
    IERC20 public usdc;
    constructor(address _usdc) { usdc = IERC20(_usdc); }
    function deposit(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external {
        usdc.transferFrom(msg.sender, address(this), amount);
    }
    function withdraw(address asset, uint256 amount, address to) external returns (uint256) {
        uint256 yieldAmount = amount * 5 / 100; // 5% yield
        uint256 totalToReturn = amount + yieldAmount;
        usdc.transfer(to, totalToReturn);
        return totalToReturn;
    }
}
"""

def main():
    """
    Simulates the full dividend cycle: investing treasury funds to generate yield,
    calculating shares based on reputation, and distributing the yield via Merkle drop.
    """
    print("--- DIVIDEND DISTRIBUTION SIMULATION ---")

    # --- 1. SETUP ---
    deployer = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    charlie = accounts[3]
    users = [alice, bob, charlie]

    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        print("Failed to load deployment addresses for dividend distribution. Exiting.")
        return

    currency_token = CurrencyToken.at(addresses["CurrencyToken"])
    rain_reputation = RainReputation.at(addresses["RainReputation"])
    treasury_v2 = TreasuryV2.at(addresses["TreasuryV2"])

    # --- 2. SIMULATE YIELD GENERATION ---
    print("\n--- Step 1: Simulating Yield Generation ---")
    
    # Deploy and whitelist the Mock Yield Source
    print("  - Deploying and whitelisting MockYieldSource...")
    mock_yield_source = Contract.from_source(MOCK_YIELD_SOURCE_CODE, "MockYieldSource")(currency_token.address, {"from": deployer})
    treasury_v2.addYieldSource(mock_yield_source.address, {"from": deployer})

    # Fund the Treasury to simulate accumulated protocol fees
    print(f"  - Funding Treasury with {CAPITAL_TO_INVEST / 10**18} DMD...")
    currency_token.mint(treasury_v2.address, CAPITAL_TO_INVEST, {"from": deployer})
    
    # Invest the capital
    print("  - Treasury investing capital...")
    treasury_v2.invest(mock_yield_source.address, CAPITAL_TO_INVEST, {"from": deployer})
    
    # Divest the capital to realize the gains
    print("  - Treasury divesting capital to realize yield...")
    balance_before_divest = currency_token.balanceOf(treasury_v2.address)
    treasury_v2.divest(mock_yield_source.address, CAPITAL_TO_INVEST, {"from": deployer})
    balance_after_divest = currency_token.balanceOf(treasury_v2.address)

    # The profit is our dividend pool
    TOTAL_DIVIDEND_AMOUNT = balance_after_divest - balance_before_divest
    print(f"  - Yield Generated (Dividend Pool): {TOTAL_DIVIDEND_AMOUNT / 10**18} DMD")

    # --- 3. OFF-CHAIN: CALCULATE DIVIDEND SHARES & BUILD MERKLE TREE ---
    print("\n--- Step 2: Off-Chain Calculation ---")
    user_addresses_for_calc = [user.address for user in users]
    
    # Use the new function from rain.dividends
    # It returns: detailed_user_shares, merkle_root_hex, total_reputation_score
    calculated_shares, merkle_root, total_calc_reputation = calculate_dividend_shares(
        rain_reputation,
        user_addresses_for_calc,
        TOTAL_DIVIDEND_AMOUNT
    )

    if total_calc_reputation == 0:
        print("No reputation found among users, skipping dividend cycle creation.")
        return

    # The `calculated_shares` list contains dicts with 'account', 'reputation', 'amount'
    # For Merkle proof generation later, we need a list of dicts with 'account' and 'amount'
    # which `calculate_dividend_shares` internally prepares for its tree construction.
    # We'll use `get_merkle_proof` which reconstructs this if needed, or pass `calculated_shares`
    # if `get_merkle_proof` is adapted to take it.
    # For now, `get_merkle_proof` re-derives leaves for consistency.

    # --- 4. ON-CHAIN: CREATE DIVIDEND CYCLE ---
    print("\n--- Step 3: On-Chain Cycle Creation ---")
    tx = treasury_v2.createDividendCycle(merkle_root, TOTAL_DIVIDEND_AMOUNT, {"from": deployer})
    cycle_id = tx.events["DividendCycleCreated"]["cycleId"]
    print(f"  - Dividend Cycle {cycle_id} created on-chain.")

    # --- 5. ON-CHAIN: SIMULATE USER CLAIMS ---
    print("\n--- Step 4: Simulating User Claims ---")
    
    # Alice's SUCCESSFUL Claim
    alice_claim_data = next(d for d in calculated_shares if d['account'] == alice.address)
    # Use get_merkle_proof from rain.dividends
    # `calculated_shares` is a list of dicts like {'account': address, 'reputation': rep, 'amount': share}
    # `get_merkle_proof` expects a list of {'account': address, 'amount': share} for all participants
    # to reconstruct the tree or find the leaf.
    # We need to pass the list of all leaves data (account, amount) that was used to build the tree.
    # This was `leaves_data_for_tree` inside `calculate_dividend_shares`.
    # Let's adjust `calculate_dividend_shares` to return this list or make `get_merkle_proof` more flexible.
    # For now, let's assume `get_merkle_proof` takes the same `calculated_shares` (which have amounts)
    # and internally extracts account/amount for proof generation.
    # This implies `get_merkle_proof` needs to be consistent with how `calculate_dividend_shares` built the tree.

    # The `leaves_data_for_tree` used in `calculate_dividend_shares` is effectively:
    # `[{'account': d['account'], 'amount': d['amount']} for d in calculated_shares]`
    all_leaves_for_proof = [{'account': d['account'], 'amount': d['amount']} for d in calculated_shares]

    alice_proof = get_merkle_proof(all_leaves_for_proof, alice_claim_data['account'], alice_claim_data['amount'])
    
    balance_before = currency_token.balanceOf(alice.address)
    treasury_v2.claimDividend(cycle_id, alice_claim_data['amount'], alice_proof, {"from": alice})
    balance_after = currency_token.balanceOf(alice.address)
    print(f"  - Alice claimed successfully. Balance increased by {(balance_after - balance_before) / 10**18} DMD.")
    assert balance_after == balance_before + alice_claim_data['amount']

    # Bob's FAILED Claim (Incorrect Amount)
    bob_claim_data = next(d for d in calculated_shares if d['account'] == bob.address)
    # Proof for the correct amount
    bob_correct_proof = get_merkle_proof(all_leaves_for_proof, bob_claim_data['account'], bob_claim_data['amount'])
    incorrect_amount = bob_claim_data['amount'] + 1 # Try to claim with a wrong amount
    
    try:
        treasury_v2.claimDividend(cycle_id, incorrect_amount, bob_correct_proof, {"from": bob})
    except Exception as e:
        assert "Invalid Merkle proof" in str(e)
        print("  - Bob's claim with incorrect amount failed as expected.")

    print("\nDividend simulation complete.")