from brownie import web3
# --- OpenZeppelin-Compatible Merkle Tree Class (Final, Corrected Version) ---

def _solidity_keccak256(types, values):
    """A wrapper for web3.solidityKeccak that is easier to use."""
    return web3.solidityKeccak(types, values)

class OZMerkleTree:
    """
    A robust Merkle Tree implementation compatible with OpenZeppelin's MerkleProof.sol.
    This version corrects the proof generation logic for levels with an odd number of nodes.
    """
    def __init__(self, leaves: list):
        # The leaves are expected to be pre-hashed. This implementation will not hash them again.
        # It sorts them to create a deterministic tree.
        self.leaves = sorted(leaves)
        
        # Build the tree levels
        self.levels = [self.leaves]
        while len(self.levels[-1]) > 1:
            self._add_level()

    def _add_level(self):
        last_level = self.levels[-1]
        next_level = []
        
        # Get nodes, duplicating the last one if the level has an odd number of nodes
        nodes = list(last_level)
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])
            
        for i in range(0, len(nodes), 2):
            node1 = nodes[i]
            node2 = nodes[i+1]
            # The core OpenZeppelin logic: sort the two nodes before hashing
            if node1 < node2:
                combined = _solidity_keccak256(['bytes32', 'bytes32'], [node1, node2])
            else:
                combined = _solidity_keccak256(['bytes32', 'bytes32'], [node2, node1])
            next_level.append(combined)
        
        self.levels.append(next_level)

    @property
    def root(self) -> bytes:
        """Returns the root of the tree."""
        return self.levels[-1][0] if self.levels and self.levels[-1] else b'\x00' * 32

    def get_proof(self, leaf: bytes) -> list:
        """Generates a Merkle proof for a given leaf (which is already hashed)."""
        try:
            # Find the index of the pre-hashed leaf in the sorted list of leaves
            index = self.leaves.index(leaf)
        except ValueError:
            raise ValueError("Leaf not found in the tree")

        proof = []
        # Iterate through the levels, from bottom to top (excluding the root level)
        for i in range(len(self.levels) - 1):
            level = self.levels[i]
            
            # *** THE CORE FIX IS HERE ***
            # We must reconstruct the list of nodes that were actually hashed at this level,
            # including the duplicated node if the level was odd.
            nodes_for_hashing = list(level)
            if len(nodes_for_hashing) % 2 == 1:
                nodes_for_hashing.append(nodes_for_hashing[-1])

            # Find the sibling in the (potentially duplicated) list of nodes
            if index % 2 == 0:
                sibling_index = index + 1
            else:
                sibling_index = index - 1
            
            proof.append(nodes_for_hashing[sibling_index])
            
            # Move to the parent's index for the next level
            index //= 2
            
        return proof