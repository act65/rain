import pytest
from brownie import RainReputation, accounts, reverts

# A pytest fixture to deploy a fresh contract instance for each test.
# This runs before each test function that includes it as an argument.
@pytest.fixture
def reputation_contract():
    """
    Deploys a new RainReputation contract.
    The deployer (accounts[0]) is automatically granted DEFAULT_ADMIN_ROLE.
    """
    # The contract is deployed by accounts[0] by default
    return RainReputation.deploy({'from': accounts[0]})

def test_deployment(reputation_contract):
    """
    Tests the initial state of the contract after deployment.
    """
    # Check the ERC721 name and symbol
    assert reputation_contract.name() == "Rain Reputation Token"
    assert reputation_contract.symbol() == "RAIN"

    # Check that the deployer has the DEFAULT_ADMIN_ROLE
    admin_role = reputation_contract.DEFAULT_ADMIN_ROLE()
    assert reputation_contract.hasRole(admin_role, accounts[0]) == True
    assert reputation_contract.hasRole(admin_role, accounts[1]) == False

def test_minting(reputation_contract):
    """
    Tests the minting of a new reputation token and state changes.
    """
    # Arrange: Define accounts and initial values
    admin = accounts[0]
    alice = accounts[1]
    initial_reputation = 100

    # Act: Admin mints a token for Alice
    tx = reputation_contract.mint(alice, initial_reputation, {'from': admin})

    # Assert: Check contract state after minting
    assert reputation_contract.ownerOf(1) == alice
    assert reputation_contract.balanceOf(alice) == 1
    assert reputation_contract.reputationScores(alice) == initial_reputation
    assert reputation_contract.totalReputation() == initial_reputation

    # Assert: Check that the correct event was emitted
    assert 'Transfer' in tx.events
    assert tx.events['Transfer']['to'] == alice
    assert tx.events['Transfer']['tokenId'] == 1

def test_mint_permissions(reputation_contract):
    """
    Ensures only an account with DEFAULT_ADMIN_ROLE can mint tokens.
    """
    # Arrange: Define a non-admin account and a recipient
    non_admin = accounts[1]
    bob = accounts[2]

    # Act & Assert: Attempt to mint from a non-admin account, expecting it to fail.
    # The 'with reverts(...)' block passes only if the code inside it fails with the expected message.
    with reverts("Admin only"):
        reputation_contract.mint(bob, 50, {'from': non_admin})

def test_non_transferable(reputation_contract):
    """
    Tests that the token is a non-transferable Soul-Bound Token (SBT).
    """
    # Arrange: Mint a token for Alice
    admin = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    reputation_contract.mint(alice, 100, {'from': admin})

    # Act & Assert: Alice attempts to transfer her token to Bob, which should be blocked.
    with reverts("RAIN: This token is non-transferable"):
        reputation_contract.transferFrom(alice, bob, 1, {'from': alice})