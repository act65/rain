import pytest
from brownie import RainReputation, ReputationUpdater, accounts, reverts

# --- Fixtures for setting up the testing environment ---

@pytest.fixture
def admin():
    """A fixture for the admin account, for clarity."""
    return accounts[0]

@pytest.fixture
def updater_account():
    """A fixture for the trusted off-chain service account."""
    return accounts[1]

@pytest.fixture
def alice():
    """A fixture for a user account."""
    return accounts[2]

@pytest.fixture
def bob():
    """A fixture for another user account."""
    return accounts[3]

@pytest.fixture
def rain_reputation_contract(admin):
    """Deploys the main RainReputation contract."""
    return RainReputation.deploy({'from': admin})

@pytest.fixture
def reputation_updater_contract(admin, rain_reputation_contract):
    """Deploys the ReputationUpdater, linking it to the RainReputation contract."""
    return ReputationUpdater.deploy(rain_reputation_contract.address, {'from': admin})

# --- Test Cases ---

def test_deployment(reputation_updater_contract, rain_reputation_contract, admin):
    """
    Tests that the ReputationUpdater contract is deployed and configured correctly.
    """
    # Check if the address of the reputation ledger was stored correctly
    assert reputation_updater_contract.rainReputation() == rain_reputation_contract.address

    # Check that the deployer received the admin role
    admin_role = reputation_updater_contract.DEFAULT_ADMIN_ROLE()
    assert reputation_updater_contract.hasRole(admin_role, admin)

def test_apply_changes_permission(reputation_updater_contract, updater_account, alice, bob):
    """
    Ensures only an account with UPDATER_ROLE can call applyReputationChanges.
    """
    # Arrange: Define some dummy data for the call
    increases = [(alice, 10, "Good deed")]
    decreases = [(bob, 5, "Minor infraction")]

    # Act & Assert: The call should fail because updater_account does not have the role yet
    with reverts("Caller is not a trusted updater"):
        reputation_updater_contract.applyReputationChanges(increases, decreases, {'from': updater_account})

def test_apply_reputation_changes(
    rain_reputation_contract,
    reputation_updater_contract,
    admin,
    updater_account,
    alice,
    bob
):
    """
    Tests the core functionality of increasing and decreasing reputation scores
    through the ReputationUpdater contract.
    """
    # --- ARRANGE ---
    # 1. Mint initial reputation for Alice and Bob in the main contract
    rain_reputation_contract.mint(alice, 100, {'from': admin})
    rain_reputation_contract.mint(bob, 100, {'from': admin})
    assert rain_reputation_contract.reputationScores(alice) == 100
    assert rain_reputation_contract.reputationScores(bob) == 100
    assert rain_reputation_contract.totalReputation() == 200

    # 2. Grant the necessary permissions (this is a critical step)
    #    a) The ReputationUpdater contract needs to be an updater on RainReputation
    rain_updater_role = rain_reputation_contract.UPDATER_ROLE()
    rain_reputation_contract.grantRole(rain_updater_role, reputation_updater_contract.address, {'from': admin})

    #    b) The external account needs to be an updater on ReputationUpdater
    updater_role = reputation_updater_contract.UPDATER_ROLE()
    reputation_updater_contract.grantRole(updater_role, updater_account, {'from': admin})

    # 3. Define the changes to be applied
    #    Note: Brownie expects a list of tuples for struct arrays
    increases = [
        (alice, 20, "Completed a major task"),
        (bob, 10, "Helped another user")
    ]
    decreases = [
        (alice, 5, "Missed a deadline")
    ]

    # --- ACT ---
    # The trusted updater_account calls the function
    tx = reputation_updater_contract.applyReputationChanges(increases, decreases, {'from': updater_account})

    # --- ASSERT ---
    # 1. Check the final reputation scores in the RainReputation contract
    # Alice: 100 + 20 - 5 = 115
    # Bob:   100 + 10 = 110
    assert rain_reputation_contract.reputationScores(alice) == 115
    assert rain_reputation_contract.reputationScores(bob) == 110

    # 2. Check the total reputation
    # Initial: 200. Changes: +20, +10, -5. Final: 225
    assert rain_reputation_contract.totalReputation() == 225

    # 3. Check that the correct events were emitted from the RainReputation contract
    # Brownie allows you to inspect events from external calls made during the transaction
    emitted_events = tx.events
    assert emitted_events['ReputationIncreased'][0]['user'] == alice
    assert emitted_events['ReputationIncreased'][0]['amount'] == 20
    assert emitted_events['ReputationIncreased'][1]['user'] == bob
    assert emitted_events['ReputationIncreased'][1]['amount'] == 10
    assert emitted_events['ReputationDecreased'][0]['user'] == alice
    assert emitted_events['ReputationDecreased'][0]['amount'] == 5

def test_apply_empty_changes(reputation_updater_contract, admin, updater_account):
    """
    Tests that the function executes successfully with empty change arrays.
    """
    # Arrange: Grant the updater role
    updater_role = reputation_updater_contract.UPDATER_ROLE()
    reputation_updater_contract.grantRole(updater_role, updater_account, {'from': admin})

    # Act: Call the function with empty arrays
    tx = reputation_updater_contract.applyReputationChanges([], [], {'from': updater_account})

    # Assert: The transaction should succeed and emit no events
    assert tx.events is None or len(tx.events) == 0