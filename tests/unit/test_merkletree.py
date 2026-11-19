"""
Claims tested: the off-chain tree produces proofs that OpenZeppelin's MerkleProof
accepts for members and rejects for non-members. Here the verifier is a Python port;
tests/test_treasury.py repeats the check against the real contract.
"""
import math

import pytest
from eth_abi.packed import encode_packed
from eth_utils import keccak
from hypothesis import given, settings, strategies as st

from rain.merkletree import EMPTY_ROOT, OZMerkleTree, hash_pair, leaf_hash, verify_proof

ADDR_A = "0x33A4622B82D4c04a53e170c638B944ce27cffce3"
ADDR_B = "0x0063046686E46Dc6F15918b61AE2B121458534a5"


def make_leaves(n):
    return [keccak(i.to_bytes(4, "big")) for i in range(n)]


# --- leaf_hash ---

@pytest.mark.parametrize("amount", [0, 1, 10**18, 2**256 - 1])
def test_leaf_hash_matches_abi_encode_packed(amount):
    expected = keccak(encode_packed(["address", "uint256"], [ADDR_A, amount]))
    assert leaf_hash(ADDR_A, amount) == expected


def test_leaf_hash_binds_account_and_amount():
    assert leaf_hash(ADDR_A, 1) != leaf_hash(ADDR_B, 1)
    assert leaf_hash(ADDR_A, 1) != leaf_hash(ADDR_A, 2)


def test_leaf_hash_ignores_address_case():
    assert leaf_hash(ADDR_A.lower(), 5) == leaf_hash(ADDR_A, 5)


@pytest.mark.parametrize("amount", [-1, 2**256])
def test_leaf_hash_rejects_non_uint256(amount):
    with pytest.raises(ValueError):
        leaf_hash(ADDR_A, amount)


# --- hash_pair ---

def test_hash_pair_is_commutative_and_sorted():
    a, b = sorted(make_leaves(2))
    assert hash_pair(a, b) == hash_pair(b, a) == keccak(a + b)


# --- tree structure ---

def test_empty_tree():
    tree = OZMerkleTree([])
    assert tree.root == EMPTY_ROOT


def test_single_leaf_tree_root_is_the_leaf_and_proof_is_empty():
    (leaf,) = make_leaves(1)
    tree = OZMerkleTree([leaf])
    assert tree.root == leaf
    assert tree.get_proof(leaf) == []


def test_two_leaf_root_known_value():
    a, b = make_leaves(2)
    assert OZMerkleTree([a, b]).root == hash_pair(a, b)


def test_three_leaf_root_known_value():
    a, b, c = sorted(make_leaves(3))
    assert OZMerkleTree([c, a, b]).root == hash_pair(hash_pair(a, b), hash_pair(c, c))


@pytest.mark.parametrize("n", range(1, 34))
def test_every_leaf_has_a_valid_proof(n):
    leaves = make_leaves(n)
    tree = OZMerkleTree(leaves)
    for leaf in leaves:
        proof = tree.get_proof(leaf)
        assert verify_proof(proof, tree.root, leaf)
        assert len(proof) == math.ceil(math.log2(n)) if n > 1 else proof == []


@pytest.mark.parametrize("n", [1, 2, 3, 4, 7, 8, 9])
def test_proofs_do_not_verify_other_leaves(n):
    leaves = make_leaves(n)
    tree = OZMerkleTree(leaves)
    outsider = keccak(b"not in the tree")
    for leaf in leaves:
        assert not verify_proof(tree.get_proof(leaf), tree.root, outsider)
    if n > 2:
        assert not verify_proof(tree.get_proof(leaves[0]), tree.root, leaves[-1])


def test_root_does_not_depend_on_leaf_order():
    leaves = make_leaves(11)
    assert OZMerkleTree(leaves).root == OZMerkleTree(list(reversed(leaves))).root


def test_changing_any_leaf_changes_the_root():
    leaves = make_leaves(6)
    root = OZMerkleTree(leaves).root
    for i in range(len(leaves)):
        changed = list(leaves)
        changed[i] = keccak(b"changed" + bytes([i]))
        assert OZMerkleTree(changed).root != root


def test_proof_for_missing_leaf_raises():
    with pytest.raises(ValueError, match="not found"):
        OZMerkleTree(make_leaves(4)).get_proof(keccak(b"missing"))


def test_duplicate_leaves_rejected():
    leaf = make_leaves(1)[0]
    with pytest.raises(ValueError, match="Duplicate"):
        OZMerkleTree([leaf, leaf])


def test_leaves_must_be_32_bytes():
    with pytest.raises(ValueError, match="32-byte"):
        OZMerkleTree([b"short"])


# --- properties ---

leaf_sets = st.sets(st.binary(min_size=32, max_size=32), min_size=1, max_size=40)


@settings(max_examples=100, deadline=None)
@given(leaves=leaf_sets, outsider=st.binary(min_size=32, max_size=32))
def test_property_members_verify_and_non_members_do_not(leaves, outsider):
    tree = OZMerkleTree(leaves)
    for leaf in leaves:
        proof = tree.get_proof(leaf)
        assert verify_proof(proof, tree.root, leaf)
        if outsider not in leaves:
            assert not verify_proof(proof, tree.root, outsider)


@settings(max_examples=50, deadline=None)
@given(leaves=leaf_sets, data=st.data())
def test_property_tampered_proof_fails(leaves, data):
    tree = OZMerkleTree(leaves)
    leaf = data.draw(st.sampled_from(sorted(leaves)))
    proof = tree.get_proof(leaf)
    if not proof:
        return
    i = data.draw(st.integers(0, len(proof) - 1))
    tampered = list(proof)
    tampered[i] = keccak(tampered[i])
    assert not verify_proof(tampered, tree.root, leaf)
