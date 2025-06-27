import pytest
from brownie import accounts, reverts, chain, web3
from brownie import Treasury, CurrencyToken, MockYieldSource

from rain.merkletree import OZMerkleTree, _solidity_keccak256

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