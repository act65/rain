# File: 04_run_dividend_distribution.py (Corrected for TreasuryV2)

from brownie import (
    accounts,
    network,
    Contract,
    CurrencyToken,
    RainReputation,
    TreasuryV2,
    web3,
)
from merkle_tree import MerkleTree # Assumes a standard merkle tree library is installed
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

    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

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
    user_data = []
    total_reputation = 0
    for user in users:
        rep = rain_reputation.reputationScores(user.address)
        if rep > 0:
            user_data.append({"account": user.address, "reputation": rep})
            total_reputation += rep
    
    leaves_data = []
    for data in user_data:
        dividend = (data["reputation"] * TOTAL_DIVIDEND_AMOUNT) // total_reputation
        leaves_data.append({"account": data["account"], "amount": dividend})
        print(f"  - Calculated share for {data['account'][:10]}...: {dividend / 10**18} DMD")

    hashed_leaves = [web3.solidityKeccak(['address', 'uint256'], [d['account'], d['amount']]) for d in leaves_data]
    merkle_tree = MerkleTree(hashed_leaves)
    merkle_root = "0x" + merkle_tree.root.hex()
    print(f"  - Built Merkle Tree. Root: {merkle_root}")

    # --- 4. ON-CHAIN: CREATE DIVIDEND CYCLE ---
    print("\n--- Step 3: On-Chain Cycle Creation ---")
    tx = treasury_v2.createDividendCycle(merkle_root, TOTAL_DIVIDEND_AMOUNT, {"from": deployer})
    cycle_id = tx.events["DividendCycleCreated"]["cycleId"]
    print(f"  - Dividend Cycle {cycle_id} created on-chain.")

    # --- 5. ON-CHAIN: SIMULATE USER CLAIMS ---
    print("\n--- Step 4: Simulating User Claims ---")
    
    # Alice's SUCCESSFUL Claim
    alice_claim_data = next(d for d in leaves_data if d['account'] == alice.address)
    alice_leaf = web3.solidityKeccak(['address', 'uint256'], [alice_claim_data['account'], alice_claim_data['amount']])
    alice_proof = merkle_tree.get_proof(alice_leaf)
    
    balance_before = currency_token.balanceOf(alice.address)
    treasury_v2.claimDividend(cycle_id, alice_claim_data['amount'], alice_proof, {"from": alice})
    balance_after = currency_token.balanceOf(alice.address)
    print(f"  - Alice claimed successfully. Balance increased by {(balance_after - balance_before) / 10**18} DMD.")
    assert balance_after == balance_before + alice_claim_data['amount']

    # Bob's FAILED Claim (Incorrect Amount)
    bob_claim_data = next(d for d in leaves_data if d['account'] == bob.address)
    bob_proof = merkle_tree.get_proof(web3.solidityKeccak(['address', 'uint256'], [bob_claim_data['account'], bob_claim_data['amount']]))
    incorrect_amount = bob_claim_data['amount'] + 1
    
    try:
        treasury_v2.claimDividend(cycle_id, incorrect_amount, bob_proof, {"from": bob})
    except Exception as e:
        assert "Invalid Merkle proof" in str(e)
        print("  - Bob's claim with incorrect amount failed as expected.")

    print("\nDividend simulation complete.")