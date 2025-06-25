import json
from merkle_trees import MerkleTree
from brownie import (
    accounts,
    Contract,
    ReputationV2_Simplified,
    TreasuryV2,
    CurrencyToken,
    web3,
)

# --- Configuration ---
# Total amount of currency to be distributed in this dividend cycle
TOTAL_DIVIDEND_AMOUNT = 1_000_000 * (10**18)  # 1,000,000 DMD

# Path to the file where deployment addresses are stored
DEPLOYMENT_ADDRESSES_FILE = "deployment_addresses.json"


def main():
    """
    Simulates the full off-chain and on-chain dividend distribution process.
    """
    print("--- Starting Dividend Simulation ---")

    # 1. Load Accounts and Contracts
    # ==============================
    owner = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    charlie = accounts[3]
    users = [alice, bob, charlie]

    with open(DEPLOYMENT_ADDRESSES_FILE) as f:
        addresses = json.load(f)

    reputation_contract = ReputationV2_Simplified.at(addresses["reputation_contract"])
    treasury_contract = TreasuryV2.at(addresses["treasury_contract"])
    token_contract = CurrencyToken.at(addresses["token_contract"])

    print(f"Loaded contracts:")
    print(f"  - ReputationV2: {reputation_contract.address}")
    print(f"  - TreasuryV2: {treasury_contract.address}")
    print(f"  - CurrencyToken (DMD): {token_contract.address}")
    print("-" * 30)

    # 2. Off-Chain: Fetch Reputations and Calculate Dividends
    # =======================================================
    print("Step 2: Fetching reputations and calculating dividend shares...")
    user_data = []
    total_reputation = 0

    for user in users:
        rep = reputation_contract.reputationScores(user.address)
        if rep > 0:
            user_data.append({"account": user, "reputation": rep})
            total_reputation += rep
        print(f"  - {user.address[:10]}... has {rep / 10**18} reputation.")

    if total_reputation == 0:
        print("\nNo reputation found among users. Cannot simulate dividends. Exiting.")
        return

    print(f"\nTotal system reputation: {total_reputation / 10**18}")

    # Calculate each user's dividend share
    leaves_data = []
    for user in user_data:
        # Using precise integer arithmetic
        dividend = (user["reputation"] * TOTAL_DIVIDEND_AMOUNT) // total_reputation
        leaves_data.append({"account": user["account"], "amount": dividend})
        print(f"  - {user['account'].address[:10]}... dividend: {dividend / 10**18} DMD")

    # 3. Off-Chain: Build the Merkle Tree
    # ===================================
    print("\nStep 3: Building Merkle Tree...")

    # The leaves must be hashed in the same way the contract will verify them
    # keccak256(abi.encodePacked(address, uint256))
    hashed_leaves = [
        web3.solidityKeccak(['address', 'uint256'], [data['account'].address, data['amount']])
        for data in leaves_data
    ]

    merkle_tree = MerkleTree(hashed_leaves)
    merkle_root = "0x" + merkle_tree.root.hex()
    print(f"  - Merkle Root: {merkle_root}")
    print("-" * 30)

    # 4. On-Chain: Fund Treasury and Create Dividend Cycle
    # ====================================================
    print("Step 4: Funding Treasury and creating dividend cycle...")

    # Ensure the Treasury has enough funds for the distribution
    print(f"  - Transferring {TOTAL_DIVIDEND_AMOUNT / 10**18} DMD to Treasury...")
    token_contract.transfer(
        treasury_contract.address, TOTAL_DIVIDEND_AMOUNT, {"from": owner}
    )
    treasury_balance = token_contract.balanceOf(treasury_contract.address)
    print(f"  - Treasury balance is now: {treasury_balance / 10**18} DMD")

    # Create the new cycle on-chain
    tx = treasury_contract.createDividendCycle(
        merkle_root, TOTAL_DIVIDEND_AMOUNT, {"from": owner}
    )
    tx.wait(1)
    cycle_id = tx.events["DividendCycleCreated"]["cycleId"]
    print(f"  - Successfully created Dividend Cycle with ID: {cycle_id}")
    print("-" * 30)

    # 5. On-Chain: Simulate User Claims
    # =================================
    print("Step 5: Simulating user claims...")

    # --- Alice's SUCCESSFUL Claim ---
    print("\n--- Alice's Claim (Success Scenario) ---")
    alice_data = next(item for item in leaves_data if item["account"] == alice)
    alice_leaf = web3.solidityKeccak(['address', 'uint256'], [alice.address, alice_data['amount']])
    alice_proof = merkle_tree.get_proof(alice_leaf)
    
    alice_balance_before = token_contract.balanceOf(alice.address)
    print(f"  - Alice's balance before claim: {alice_balance_before / 10**18} DMD")

    # Alice calls the claim function with her proof
    claim_tx = treasury_contract.claimDividend(
        cycle_id, alice_data["amount"], alice_proof, {"from": alice}
    )
    claim_tx.wait(1)
    print("  - Alice submitted her claim successfully!")

    alice_balance_after = token_contract.balanceOf(alice.address)
    print(f"  - Alice's balance after claim:  {alice_balance_after / 10**18} DMD")
    assert alice_balance_after == alice_balance_before + alice_data["amount"]
    print("  - VERIFIED: Alice received the correct dividend amount.")

    # --- Bob's FAILED Claim (Incorrect Amount) ---
    print("\n--- Bob's Claim (Failure Scenario) ---")
    bob_data = next(item for item in leaves_data if item["account"] == bob)
    bob_leaf = web3.solidityKeccak(['address', 'uint256'], [bob.address, bob_data['amount']])
    bob_proof = merkle_tree.get_proof(bob_leaf)
    
    incorrect_amount = bob_data["amount"] + 1 # Try to claim 1 wei more
    print(f"  - Bob will attempt to claim {incorrect_amount / 10**18} DMD (incorrect amount).")

    try:
        treasury_contract.claimDividend(
            cycle_id, incorrect_amount, bob_proof, {"from": bob}
        )
    except Exception as e:
        print("  - As expected, Bob's claim failed.")
        # Brownie/Ganache revert reason is often in the message
        assert "Invalid Merkle proof" in str(e)
        print("  - VERIFIED: Transaction reverted with 'Invalid Merkle proof'.")

    print("\n--- Dividend Simulation Complete ---")