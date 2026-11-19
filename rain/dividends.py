"""
Off-chain logic for the Reputation Dividend: pro-rata shares and the Merkle drop.

``compute_shares`` and ``build_tree`` are pure. The remaining functions take contract
objects (Ape contracts in practice) and only call their public getters / events.
"""

from typing import Any, Dict, List, Mapping, Optional, Tuple

from rain.merkletree import EMPTY_ROOT, OZMerkleTree, leaf_hash


def compute_shares(reputations: Mapping[str, int], total_dividend_amount: int) -> Dict[str, int]:
    """
    Splits ``total_dividend_amount`` pro rata to reputation, rounding each share down.

    Accounts with zero reputation, or whose share rounds down to zero, are left out.
    The shares therefore sum to at most ``total_dividend_amount``; the remainder
    ("dust", less than one base unit per account) stays in the Treasury.
    """
    if total_dividend_amount < 0:
        raise ValueError("total_dividend_amount must be non-negative")
    if any(rep < 0 for rep in reputations.values()):
        raise ValueError("reputation must be non-negative")

    total_reputation = sum(reputations.values())
    if total_reputation == 0:
        return {}

    shares = {}
    for account, rep in reputations.items():
        share = (rep * total_dividend_amount) // total_reputation
        if share > 0:
            shares[account] = share
    return shares


def build_tree(shares: Mapping[str, int]) -> OZMerkleTree:
    """Builds the Merkle tree whose leaves are ``keccak(account, amount)``."""
    return OZMerkleTree([leaf_hash(account, amount) for account, amount in shares.items()])


def get_reputation_holders(
    rain_reputation_contract: Any, from_block: int = 0, to_block: Optional[int] = None
) -> List[str]:
    """
    Every account that has been minted a reputation SBT, in mint order.

    The SBT is non-transferable, so its mint (``Transfer`` from the zero address)
    events enumerate the protocol's users.
    """
    transfers = rain_reputation_contract.Transfer
    if to_block is None:
        to_block = transfers.chain_manager.blocks.height
    holders = []
    for event in transfers.range(from_block, to_block + 1):  # `range` excludes its stop block
        account = event.event_arguments["to"]
        if account not in holders:
            holders.append(account)
    return holders


def calculate_dividend_shares(
    rain_reputation_contract: Any,
    user_addresses: List[str],
    total_dividend_amount: int,
) -> Tuple[List[Dict[str, Any]], str, int]:
    """
    Reads reputations on-chain, computes dividend shares and the Merkle root.

    Returns:
        - a list of ``{"account", "reputation", "amount"}`` dicts, one per account
          with a non-zero share (these are exactly the leaves of the tree);
        - the Merkle root as a 0x-prefixed hex string;
        - the total reputation of ``user_addresses``.
    """
    reputations = {}
    for account in dict.fromkeys(str(a) for a in user_addresses):  # de-duplicate, keep order
        reputations[account] = rain_reputation_contract.reputationScores(account)
    total_reputation = sum(reputations.values())

    shares = compute_shares(reputations, total_dividend_amount)
    detailed = [
        {"account": account, "reputation": reputations[account], "amount": amount}
        for account, amount in shares.items()
    ]
    root = build_tree(shares).root if shares else EMPTY_ROOT
    return detailed, "0x" + root.hex(), total_reputation


def get_merkle_proof(leaves_data: List[Dict[str, Any]], user_address: str, user_amount: int) -> List[str]:
    """
    The Merkle proof for ``(user_address, user_amount)``.

    Args:
        leaves_data: dicts with "account" and "amount" for *all* participants (e.g. the
            list returned by ``calculate_dividend_shares``).

    Returns:
        The proof as a list of 0x-prefixed hex strings.
    """
    tree = OZMerkleTree([leaf_hash(d["account"], d["amount"]) for d in leaves_data])
    proof = tree.get_proof(leaf_hash(user_address, user_amount))
    return ["0x" + node.hex() for node in proof]
