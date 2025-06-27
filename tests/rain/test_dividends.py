import pytest
from unittest.mock import MagicMock, patch

from brownie import web3 # For web3.solidityKeccak, used in dividends.py

# Try to use pymerkle.MerkleTree as the merkle_tree dependency
try:
    from pymerkle.tree import MerkleTree as PyMerkleTree
    # The rain/dividends.py uses a MerkleTree that might be different.
    # We'll attempt to adapt or mock. For now, let's see if pymerkle can be used.
    # It seems rain/dividends.py expects a MerkleTree class that takes raw hashed leaves.
    # PyMerkleTree hashes them by default. We might need a wrapper or careful usage.
    # PyMerkleTree's root is .root, get_proof is .get_merkle_proof(leaf_hash)
except ImportError:
    PyMerkleTree = None

from rain.dividends import calculate_dividend_shares, get_merkle_proof

# --- Mock Objects ---

class MockRainReputationContract:
    def __init__(self, reputation_scores: dict):
        # reputation_scores maps address to score
        self.reputation_scores_map = reputation_scores

    def reputationScores(self, user_address: str) -> int:
        return self.reputation_scores_map.get(user_address, 0)

# --- Helper Functions ---
def hash_leaf_for_pymerkle(account: str, amount: int) -> bytes:
    """Hashes leaf data in the way rain/dividends.py expects before tree construction."""
    return web3.solidity_keccak(['address', 'uint256'], [account, amount])

# --- Test Cases ---

@pytest.fixture
def mock_users():
    return {
        "alice": "0x1111111111111111111111111111111111111111", # web3.to_checksum_address(...) later
        "bob":   "0x2222222222222222222222222222222222222222",
        "charlie": "0x3333333333333333333333333333333333333333",
        "david_no_rep": "0x4444444444444444444444444444444444444444"
    }

@pytest.fixture
def checksummed_mock_users(mock_users):
    return {name: web3.to_checksum_address(addr) for name, addr in mock_users.items()}


# We need to patch 'merkle_tree.MerkleTree' as used in rain.dividends
# Let's define a mock MerkleTree that behaves as expected by rain.dividends.py
class MockInternalMerkleTree:
    def __init__(self, hashed_leaves: list):
        self.hashed_leaves = sorted(hashed_leaves) # rain/dividends.py doesn't sort, but OZMerkleTree did.
                                                  # The actual merkle_tree lib might or might not.
                                                  # For consistency with OZMerkleTree, let's sort.
                                                  # If rain/dividends.py's target library doesn't sort,
                                                  # then this mock needs to reflect that.
                                                  # The important part is that it uses pre-hashed leaves.

        # Simplified tree construction for mock - actual hashing logic is complex
        if not self.hashed_leaves:
            self._root = b'\x00' * 32
        elif len(self.hashed_leaves) == 1:
            self._root = self.hashed_leaves[0]
        else:
            # This is a placeholder root calculation. # Corrected below
            # A real test would need a more accurate mock or use the actual library if compatible.
            # temp_hash = self.hashed_leaves[0]
            # for i in range(1, len(self.hashed_leaves)):
            #     if temp_hash < self.hashed_leaves[i]:
            #         temp_hash = web3.solidity_keccak(['bytes32', 'bytes32'], [temp_hash, self.hashed_leaves[i]])
            #     else:
            #         temp_hash = web3.solidity_keccak(['bytes32', 'bytes32'], [self.hashed_leaves[i], temp_hash])
            # self._root = temp_hash
            pass # Root will be derived from levels

        # Store leaves for get_proof
        # Logic from OZMerkleTree to build levels for get_proof
        if not self.hashed_leaves: # Handle empty tree case for levels
             self.levels = [[]]
        else:
            self.levels = [list(self.hashed_leaves)] # Start with a copy of the sorted leaves
            while len(self.levels[-1]) > 1:
                last_level_nodes = self.levels[-1]
                next_level_nodes = []

                nodes_to_hash = list(last_level_nodes) # Use a copy for modification
                if len(nodes_to_hash) % 2 == 1:
                    nodes_to_hash.append(nodes_to_hash[-1]) # Duplicate last if odd

                for i in range(0, len(nodes_to_hash), 2):
                    n1, n2 = nodes_to_hash[i], nodes_to_hash[i+1]
                    # Mimic OZMerkleTree conditional hashing order
                    if n1 < n2:
                        combined = web3.solidity_keccak(['bytes32', 'bytes32'], [n1, n2])
                    else:
                        combined = web3.solidity_keccak(['bytes32', 'bytes32'], [n2, n1])
                    next_level_nodes.append(combined)
                self.levels.append(next_level_nodes)

        if not self.levels or not self.levels[-1]:
            self._root = b'\x00' * 32
        else:
            self._root = self.levels[-1][0]


    @property
    def root(self):
        return self._root

    def get_proof(self, leaf_hash: bytes) -> list:
        # Simplified proof generation, mirrors OZMerkleTree logic
        try:
            # Proof generation should use the initial sorted list of leaves (self.hashed_leaves)
            # to find the original index, NOT self.levels[0] if it was further processed.
            # In this mock, self.hashed_leaves is the sorted list, and self.levels[0] is a copy of it.
            index = self.hashed_leaves.index(leaf_hash)
        except ValueError:
            # Behavior of external lib might differ, this mimics OZMerkleTree
            raise ValueError("Leaf not found in the tree for proof")

        proof = []
        for i in range(len(self.levels) - 1):
            level_nodes = self.levels[i]

            nodes_for_hashing_at_level = list(level_nodes)
            if len(nodes_for_hashing_at_level) % 2 == 1:
                nodes_for_hashing_at_level.append(nodes_for_hashing_at_level[-1])

            if index % 2 == 0:
                sibling_index = index + 1
            else:
                sibling_index = index - 1

            if sibling_index < len(nodes_for_hashing_at_level):
                 proof.append(nodes_for_hashing_at_level[sibling_index])
            # Else: if sibling_index is out of bounds, it means this node was duplicated
            # and its "sibling" was itself. In some proof formats, this isn't added.
            # OZMerkleTree always added it. We'll follow that.
            # Let's assume the external lib would also provide the duplicated node as sibling
            elif len(nodes_for_hashing_at_level) == index +1 : # it was the duplicated one
                 proof.append(nodes_for_hashing_at_level[index])


            index //= 2
        return proof


@patch('rain.dividends.MerkleTree', MockInternalMerkleTree) # Patch where it's looked up
def test_calculate_dividend_shares_basic(checksummed_mock_users):
    users = checksummed_mock_users
    mock_rep_contract = MockRainReputationContract({
        users["alice"]: 100 * 10**18, # 100 Rep
        users["bob"]:   200 * 10**18, # 200 Rep
        users["charlie"]: 0,           # 0 Rep (should be filtered out by score > 0)
        # david_no_rep is not in map, will get 0
    })
    user_addresses = [users["alice"], users["bob"], users["charlie"], users["david_no_rep"]]
    total_dividend = 3000 * 10**18 # 3000 DMD

    shares, merkle_root_hex, total_rep = calculate_dividend_shares(
        mock_rep_contract, user_addresses, total_dividend
    )

    assert total_rep == (100 + 200) * 10**18 # 300 Rep total from Alice and Bob

    assert len(shares) == 2 # Only Alice and Bob have reputation > 0

    alice_share_info = next(s for s in shares if s["account"] == users["alice"])
    bob_share_info = next(s for s in shares if s["account"] == users["bob"])

    # Alice: (100 / 300) * 3000 = 1000 DMD
    # Bob:   (200 / 300) * 3000 = 2000 DMD
    assert alice_share_info["reputation"] == 100 * 10**18
    assert alice_share_info["amount"] == pytest.approx(1000 * 10**18)

    assert bob_share_info["reputation"] == 200 * 10**18
    assert bob_share_info["amount"] == pytest.approx(2000 * 10**18)

    # Verify Merkle Root (depends on MockInternalMerkleTree's accuracy)
    expected_leaves_data_for_tree = [
        {"account": users["alice"], "amount": 1000 * 10**18},
        {"account": users["bob"], "amount": 2000 * 10**18},
    ]
    # Sort by account for deterministic hashing if MockInternalMerkleTree sorts leaves
    # The current MockInternalMerkleTree sorts the pre-hashed leaves.
    # rain.dividends.py does not sort leaves_data_for_tree before hashing.
    # To match rain.dividends.py, the mock shouldn't sort or test should match its order.
    # For now, let's assume an order for the mock.
    # The order of `user_data` in `calculate_dividend_shares` is based on `user_addresses` input order.
    # Alice, Bob were processed.

    hashed_leaves_for_mock = [
        hash_leaf_for_pymerkle(users["alice"], 1000 * 10**18),
        hash_leaf_for_pymerkle(users["bob"], 2000 * 10**18),
    ]
    # Our MockInternalMerkleTree sorts these hashed_leaves.
    mock_tree = MockInternalMerkleTree(hashed_leaves_for_mock)
    expected_root = "0x" + mock_tree.root.hex()
    assert merkle_root_hex == expected_root


@patch('rain.dividends.MerkleTree', MockInternalMerkleTree)
def test_calculate_dividend_shares_no_eligible_users(checksummed_mock_users):
    users = checksummed_mock_users
    mock_rep_contract = MockRainReputationContract({
        users["alice"]: 0,
        users["bob"]: 0,
    })
    user_addresses = [users["alice"], users["bob"]]
    total_dividend = 1000 * 10**18

    shares, merkle_root_hex, total_rep = calculate_dividend_shares(
        mock_rep_contract, user_addresses, total_dividend
    )

    assert shares == []
    assert total_rep == 0
    # Empty tree root from MockInternalMerkleTree
    mock_empty_tree = MockInternalMerkleTree([])
    assert merkle_root_hex == "0x" + mock_empty_tree.root.hex()


@patch('rain.dividends.MerkleTree', MockInternalMerkleTree)
def test_get_merkle_proof_basic(checksummed_mock_users):
    users = checksummed_mock_users
    # Data used to build the tree in calculate_dividend_shares
    leaves_data = [
        {"account": users["alice"], "amount": 1000 * 10**18},
        {"account": users["bob"], "amount": 2000 * 10**18},
        {"account": users["charlie"], "amount": 500 * 10**18} # Charlie added for this test
    ]

    # User for whom we want the proof
    target_user_address = users["bob"]
    target_user_amount = 2000 * 10**18

    proof_hex = get_merkle_proof(leaves_data, target_user_address, target_user_amount)

    assert isinstance(proof_hex, list)
    for p_item in proof_hex:
        assert isinstance(p_item, str)
        assert p_item.startswith("0x")

    # Verify the proof (optional, but good for confidence in the mock)
    # Rebuild the tree with MockInternalMerkleTree using the exact same leaves_data order
    hashed_leaves = [hash_leaf_for_pymerkle(d['account'], d['amount']) for d in leaves_data]

    # Ensure MockInternalMerkleTree is consistent with how rain.dividends.py uses it.
    # rain.dividends.py does not sort `leaves_data` before hashing.
    # So, MockInternalMerkleTree should also operate on the given order of hashed_leaves
    # if its `__init__` doesn't sort. Our current MockInternalMerkleTree sorts.
    # This means the proof generation needs to be from a tree built with sorted leaves.

    # Let's make the MockInternalMerkleTree init consistent with OZMerkleTree (sorts pre-hashed leaves)
    # And ensure leaves_data for proof generation is consistent.

    mock_tree_for_proof_verify = MockInternalMerkleTree(hashed_leaves) # Uses sorted list of hashes

    target_leaf_hash = hash_leaf_for_pymerkle(target_user_address, target_user_amount)

    # Simplified verify_merkle_proof (as used in test_merkletree.py)
    def verify_mock_proof(root: bytes, leaf: bytes, proof_bytes: list) -> bool:
        current_hash = leaf
        for sibling_bytes in proof_bytes:
            if current_hash < sibling_bytes:
                current_hash = web3.solidity_keccak(['bytes32', 'bytes32'], [current_hash, sibling_bytes])
            else:
                current_hash = web3.solidity_keccak(['bytes32', 'bytes32'], [sibling_bytes, current_hash])
        return current_hash == root

    proof_bytes_for_verify = [bytes.fromhex(p[2:]) for p in proof_hex]
    assert verify_mock_proof(mock_tree_for_proof_verify.root, target_leaf_hash, proof_bytes_for_verify)


@patch('rain.dividends.MerkleTree', None) # Simulate MerkleTree library not being found
def test_functions_raise_env_error_if_merkle_lib_missing(checksummed_mock_users):
    users = checksummed_mock_users
    mock_rep_contract = MockRainReputationContract({users["alice"]: 100})

    with pytest.raises(EnvironmentError, match="MerkleTree library is not installed"):
        calculate_dividend_shares(mock_rep_contract, [users["alice"]], 1000)

    with pytest.raises(EnvironmentError, match="MerkleTree library is not installed"):
        get_merkle_proof([{"account": users["alice"], "amount": 100}], users["alice"], 100)

# TODO: Test get_merkle_proof for a leaf not in the tree (should it raise error or return empty proof?)
# The current MockInternalMerkleTree.get_proof raises ValueError, similar to OZMerkleTree.
# The actual 'merkle_tree' library might behave differently.
# For now, this behavior is consistent with the mock.

@patch('rain.dividends.MerkleTree', MockInternalMerkleTree)
def test_get_merkle_proof_leaf_not_found(checksummed_mock_users):
    users = checksummed_mock_users
    leaves_data = [
        {"account": users["alice"], "amount": 1000 * 10**18},
    ]
    with pytest.raises(ValueError): # Assuming the mocked/actual tree raises ValueError
         get_merkle_proof(leaves_data, users["bob"], 2000 * 10**18)
