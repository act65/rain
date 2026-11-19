"""
A Merkle tree compatible with OpenZeppelin's ``MerkleProof.sol`` (sorted-pair hashing).

This module is pure Python: it needs ``eth_utils`` for keccak but no chain connection,
so it can be unit tested (and used) without a chain.
"""

from typing import Iterable, List

from eth_utils import keccak, to_canonical_address

EMPTY_ROOT = b"\x00" * 32


def leaf_hash(account, amount: int) -> bytes:
    """
    The leaf used by ``Treasury.claimDividend``:
    ``keccak256(abi.encodePacked(address account, uint256 amount))``.
    """
    amount = int(amount)
    if amount < 0 or amount >= 2**256:
        raise ValueError(f"amount {amount} does not fit in a uint256")
    return keccak(to_canonical_address(str(account)) + amount.to_bytes(32, "big"))


def hash_pair(a: bytes, b: bytes) -> bytes:
    """OpenZeppelin's commutative node hash: the smaller node goes first."""
    return keccak(a + b) if a <= b else keccak(b + a)


def verify_proof(proof: Iterable[bytes], root: bytes, leaf: bytes) -> bool:
    """A Python port of ``MerkleProof.verify`` (used to test the tree off-chain)."""
    computed = bytes(leaf)
    for sibling in proof:
        computed = hash_pair(computed, bytes(sibling))
    return computed == bytes(root)


class OZMerkleTree:
    """
    Builds a tree over pre-hashed 32-byte leaves.

    Leaves are sorted so that the tree does not depend on input order. A level with
    an odd number of nodes pairs its last node with itself.
    """

    def __init__(self, leaves: Iterable[bytes]):
        leaves = [bytes(leaf) for leaf in leaves]
        for leaf in leaves:
            if len(leaf) != 32:
                raise ValueError("Leaves must be 32-byte hashes")
        if len(set(leaves)) != len(leaves):
            # Two identical leaves could only be claimed once on-chain.
            raise ValueError("Duplicate leaves are not allowed")

        self.leaves: List[bytes] = sorted(leaves)
        self.levels: List[List[bytes]] = [self.leaves]
        while len(self.levels[-1]) > 1:
            self.levels.append(self._next_level(self.levels[-1]))

    @staticmethod
    def _padded(level: List[bytes]) -> List[bytes]:
        return level + [level[-1]] if len(level) % 2 == 1 else level

    @classmethod
    def _next_level(cls, level: List[bytes]) -> List[bytes]:
        nodes = cls._padded(level)
        return [hash_pair(nodes[i], nodes[i + 1]) for i in range(0, len(nodes), 2)]

    @property
    def root(self) -> bytes:
        """The root of the tree (32 zero bytes for an empty tree)."""
        return self.levels[-1][0] if self.leaves else EMPTY_ROOT

    def get_proof(self, leaf: bytes) -> List[bytes]:
        """The proof (list of sibling hashes, bottom to top) for a pre-hashed leaf."""
        try:
            index = self.leaves.index(bytes(leaf))
        except ValueError:
            raise ValueError("Leaf not found in the tree")

        proof = []
        for level in self.levels[:-1]:
            nodes = self._padded(level)
            proof.append(nodes[index ^ 1])
            index //= 2
        return proof
