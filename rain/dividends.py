# rain/dividends.py

"""
Core off-chain logic for calculating and preparing dividend distributions.
"""

from brownie import web3 # For web3.solidityKeccak
from typing import List, Dict, Any, Tuple

# It's good practice to ensure external dependencies like merkle_tree are explicitly handled.
# For now, we assume it's available in the environment.
try:
    from merkle_tree import MerkleTree
except ImportError:
    # Provide a fallback or raise a more informative error if merkle_tree is critical
    print("Warning: merkle_tree library not found. Dividend calculation requiring Merkle trees will fail.")
    MerkleTree = None

def calculate_dividend_shares(
    rain_reputation_contract: Any, # Brownie Contract object for RainReputation
    user_addresses: List[str],
    total_dividend_amount: int
) -> Tuple[List[Dict[str, Any]], str, int]:
    """
    Calculates individual dividend shares based on user reputation and prepares a Merkle tree.

    Args:
        rain_reputation_contract: The deployed RainReputation Brownie contract instance.
        user_addresses: A list of user addresses to calculate shares for.
        total_dividend_amount: The total amount of dividends to be distributed.

    Returns:
        A tuple containing:
        - A list of dictionaries, each with "account", "reputation", and "amount" (dividend share).
        - The Merkle root (hex string).
        - The total reputation of the participating users.
    """
    if MerkleTree is None:
        raise EnvironmentError("MerkleTree library is not installed, cannot calculate dividend shares.")

    user_data = []
    total_reputation_score = 0
    print("  - [Core Logic] Fetching reputations for dividend calculation...")
    for user_address in user_addresses:
        # Ensure rep is fetched using the passed contract instance
        rep = rain_reputation_contract.reputationScores(user_address)
        if rep > 0:
            user_data.append({"account": user_address, "reputation": rep})
            total_reputation_score += rep
            print(f"    - User {user_address[:10]}... Reputation: {rep / 10**18}")
        else:
            print(f"    - User {user_address[:10]}... has 0 reputation, skipping.")

    if total_reputation_score == 0:
        print("  - [Core Logic] Total reputation of participating users is 0. No dividends to distribute.")
        return [], "0x" + MerkleTree([]).root.hex() if MerkleTree else "0x0", 0


    leaves_data_for_tree = []
    detailed_user_shares = []

    print("  - [Core Logic] Calculating individual dividend shares...")
    for data in user_data:
        dividend = 0
        if total_reputation_score > 0 : # Avoid division by zero
            dividend = (data["reputation"] * total_dividend_amount) // total_reputation_score

        leaves_data_for_tree.append({"account": data["account"], "amount": dividend})
        detailed_user_shares.append({
            "account": data["account"],
            "reputation": data["reputation"],
            "amount": dividend  # This is the calculated share
        })
        print(f"    - Calculated share for {data['account'][:10]}...: {dividend / 10**18} DMD (Rep: {data['reputation'] / 10**18})")

    # Prepare leaves for the Merkle tree
    hashed_leaves = [
        web3.solidityKeccak(['address', 'uint256'], [d['account'], d['amount']])
        for d in leaves_data_for_tree
    ]

    merkle_tree_instance = MerkleTree(hashed_leaves)
    merkle_root_hex = "0x" + merkle_tree_instance.root.hex()
    print(f"  - [Core Logic] Built Merkle Tree. Root: {merkle_root_hex}")

    return detailed_user_shares, merkle_root_hex, total_reputation_score


def get_merkle_proof(
    leaves_data: List[Dict[str, Any]], # Should contain account and amount for all participants
    user_address: str,
    user_amount: int
) -> List[str]:
    """
    Generates a Merkle proof for a specific user and their amount.

    Args:
        leaves_data: A list of all leaf data (dictionaries with "account" and "amount") used to build the tree.
        user_address: The address of the user to generate the proof for.
        user_amount: The amount for the user (must match the amount used in tree construction).

    Returns:
        A list of hex strings representing the Merkle proof.
    """
    if MerkleTree is None:
        raise EnvironmentError("MerkleTree library is not installed, cannot generate Merkle proof.")

    hashed_leaves = [
        web3.solidityKeccak(['address', 'uint256'], [d['account'], d['amount']])
        for d in leaves_data
    ]
    merkle_tree_instance = MerkleTree(hashed_leaves)

    user_leaf = web3.solidityKeccak(['address', 'uint256'], [user_address, user_amount])
    proof = merkle_tree_instance.get_proof(user_leaf)

    # Convert bytes to hex strings for easier use, especially with Brownie/Web3.py
    return ["0x" + p.hex() for p in proof]
