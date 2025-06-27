import pytest
from brownie import accounts, reverts, chain, web3
from brownie import Treasury, CurrencyToken, MockYieldSource

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

# --- Fixtures for Setup ---

@pytest.fixture(scope="function")
def usdc():
    token = CurrencyToken.deploy({'from': accounts[0]})
    for i in range(4):
        token.mint(accounts[i], 1_000_000 * 10**18, {'from': accounts[0]})
    return token

@pytest.fixture(scope="function")
def mock_yield_source():
    return MockYieldSource.deploy({'from': accounts[0]})

@pytest.fixture(scope="function")
def treasury(usdc):
    claim_period = 7 * 24 * 60 * 60
    return Treasury.deploy(usdc.address, claim_period, {'from': accounts[0]})

# --- Test Cases ---

def test_dividend_cycle_full_lifecycle(treasury, usdc):
    """
    Tests the entire dividend process using the robust OZMerkleTree class.
    """
    # --- 1. Setup and Off-chain Merkle Tree Generation ---
    manager, alice, bob, charlie = accounts[0], accounts[1], accounts[2], accounts[3]
    
    reward_data = [
        (alice.address, 1000 * 10**18),
        (bob.address, 1500 * 10**18),
        (charlie.address, 500 * 10**18)
    ]
    total_rewards = sum(item[1] for item in reward_data)
    
    usdc.transfer(treasury.address, total_rewards, {'from': manager})
    
    # Create the single-hashed leaves for the tree
    leaves = [_solidity_keccak256(['address', 'uint256'], [addr, amount]) for addr, amount in reward_data]
    
    # Instantiate the Merkle tree with the pre-hashed leaves
    tree = OZMerkleTree(leaves)
    merkle_root = tree.root

    # --- 2. On-chain Cycle Creation ---
    tx = treasury.createDividendCycle(merkle_root, total_rewards, {'from': manager})
    cycle_id = tx.events['DividendCycleCreated']['cycleId']
    
    # Sanity check the root
    assert treasury.getCycleDetails(cycle_id)['merkleRoot'].hex() == merkle_root.hex().replace("0x", "")

    # --- 3. Valid User Claims ---
    # Claim for Alice
    alice_leaf = _solidity_keccak256(['address', 'uint256'], [alice.address, 1000 * 10**18])
    alice_proof = tree.get_proof(alice_leaf)
    alice_initial_balance = usdc.balanceOf(alice)
    
    treasury.claimDividend(cycle_id, 1000 * 10**18, alice_proof, {'from': alice})
    assert usdc.balanceOf(alice) == alice_initial_balance + (1000 * 10**18)
    assert treasury.hasUserClaimed(cycle_id, alice) == True

    # Claim for Charlie (tests odd-numbered node logic)
    charlie_leaf = _solidity_keccak256(['address', 'uint256'], [charlie.address, 500 * 10**18])
    charlie_proof = tree.get_proof(charlie_leaf)
    charlie_initial_balance = usdc.balanceOf(charlie)

    treasury.claimDividend(cycle_id, 500 * 10**18, charlie_proof, {'from': charlie})
    assert usdc.balanceOf(charlie) == charlie_initial_balance + (500 * 10**18)
    assert treasury.hasUserClaimed(cycle_id, charlie) == True

    # --- 4. Invalid Claims ---
    with reverts("Dividend already claimed for this cycle"):
        treasury.claimDividend(cycle_id, 1000 * 10**18, alice_proof, {'from': alice})
        
    bob_reward = 1500 * 10**18
    with reverts("Invalid Merkle proof"):
        treasury.claimDividend(cycle_id, bob_reward, alice_proof, {'from': bob})

    # --- 5. Claiming after Expiry ---
    claim_period = treasury.claimPeriodDuration()
    chain.sleep(claim_period + 100)
    chain.mine()
    
    bob_leaf = _solidity_keccak256(['address', 'uint256'], [bob.address, bob_reward])
    bob_proof = tree.get_proof(bob_leaf)
    with reverts("Dividend cycle has expired"):
        treasury.claimDividend(cycle_id, bob_reward, bob_proof, {'from': bob})