import pytest
from helpers import accounts, deploy_reputation, ev, project, reverts, seed_reputation

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
    return deploy_reputation(admin)

@pytest.fixture
def reputation_updater_contract(admin, rain_reputation_contract):
    """Deploys the ReputationUpdater, linking it to the RainReputation contract."""
    return project.ReputationUpdater.deploy(rain_reputation_contract.address, sender=admin)

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
    decreases = [(bob, 5, "Broke a promise")]

    # Act & Assert: The call should fail because updater_account does not have the role yet
    with reverts("Caller is not a trusted updater"):
        reputation_updater_contract.applyReputationChanges(increases, decreases, sender=updater_account)

def test_apply_reputation_changes(
    rain_reputation_contract,
    reputation_updater_contract,
    admin,
    updater_account,
    alice,
    bob
):
    """
    Tests the core functionality of crediting kept promises and recording broken ones
    through the ReputationUpdater contract.
    """
    # --- ARRANGE ---
    # 1. Mint initial reputation for Alice and Bob in the main contract
    seed_reputation(rain_reputation_contract, admin, alice, 100)
    seed_reputation(rain_reputation_contract, admin, bob, 100)
    assert rain_reputation_contract.reputationScores(alice) == 100
    assert rain_reputation_contract.reputationScores(bob) == 100
    assert rain_reputation_contract.totalReputation() == 200

    # 2. Grant the necessary permissions (this is a critical step)
    #    a) The ReputationUpdater contract needs to be an updater on RainReputation
    rain_updater_role = rain_reputation_contract.UPDATER_ROLE()
    rain_reputation_contract.grantRole(rain_updater_role, reputation_updater_contract.address, sender=admin)

    #    b) The external account needs to be an updater on ReputationUpdater
    updater_role = reputation_updater_contract.UPDATER_ROLE()
    reputation_updater_contract.grantRole(updater_role, updater_account, sender=admin)

    # 3. Define the changes to be applied
    #    Note: struct arrays are passed as a list of tuples
    increases = [
        (alice, 20, "Completed a major task"),
        (bob, 10, "Helped another user")
    ]
    decreases = [
        (alice, 5, "Missed a deadline")
    ]

    # --- ACT ---
    # The trusted updater_account calls the function
    tx = reputation_updater_contract.applyReputationChanges(increases, decreases, sender=updater_account)

    # --- ASSERT ---
    # 1. Check the final reputation scores in the RainReputation contract
    # Alice: 100 + 20 = 120, with 5 on her broken-promise counter (which does not reduce her reputation)
    # Bob:   100 + 10 = 110
    assert rain_reputation_contract.reputationScores(alice) == 120
    assert rain_reputation_contract.brokenScores(alice) == 5
    assert rain_reputation_contract.reputationScores(bob) == 110
    assert rain_reputation_contract.brokenScores(bob) == 0

    # 2. Check the total reputation
    # Initial: 200. Changes: +20, +10. Final: 230
    assert rain_reputation_contract.totalReputation() == 230

    # 3. Check that the correct events were emitted from the RainReputation contract
    # The receipt includes events from external calls made during the transaction
    emitted_events = ev(tx)
    assert emitted_events['ReputationIncreased'][0]['user'] == alice
    assert emitted_events['ReputationIncreased'][0]['amount'] == 20
    assert emitted_events['ReputationIncreased'][1]['user'] == bob
    assert emitted_events['ReputationIncreased'][1]['amount'] == 10
    assert emitted_events['BrokenPromiseRecorded'][0]['user'] == alice
    assert emitted_events['BrokenPromiseRecorded'][0]['amount'] == 5

def test_apply_empty_changes(reputation_updater_contract, admin, updater_account):
    """
    Tests that the function executes successfully with empty change arrays.
    """
    # Arrange: Grant the updater role
    updater_role = reputation_updater_contract.UPDATER_ROLE()
    reputation_updater_contract.grantRole(updater_role, updater_account, sender=admin)

    # Act: Call the function with empty arrays
    tx = reputation_updater_contract.applyReputationChanges([], [], sender=updater_account)

    # Assert: The transaction should succeed and emit no events
    assert len(tx.events) == 0


# =====================================================================================
# Each update is applied at most once, and one bad entry never blocks a batch
# =====================================================================================

@pytest.fixture
def wired(rain_reputation_contract, reputation_updater_contract, admin, updater_account, alice, bob):
    """Roles granted, Alice and Bob at 100 reputation, accounts[8] standing in for the RCT contract."""
    rep, updater = rain_reputation_contract, reputation_updater_contract
    rep.grantRole(rep.UPDATER_ROLE(), updater.address, sender=admin)
    updater.grantRole(updater.UPDATER_ROLE(), updater_account, sender=admin)
    rep.setRctContract(accounts[8], sender=admin)
    seed_reputation(rep, admin, alice, 100)
    seed_reputation(rep, admin, bob, 100)
    return rep, updater


def test_replayed_batch_is_skipped(wired, updater_account, alice, bob):
    rep, updater = wired
    increases = [(alice, 25, "PROMISE_FULFILLED:1")]
    decreases = [(bob, 40, "PROMISE_DEFAULTED:2")]

    updater.applyReputationChanges(increases, decreases, sender=updater_account)
    tx = updater.applyReputationChanges(increases, decreases, sender=updater_account)

    assert rep.reputationScores(alice) == 125 and rep.reputationScores(bob) == 100
    assert rep.brokenScores(bob) == 40  # recorded once
    assert rep.totalReputation() == 225
    assert 'ReputationIncreased' not in ev(tx) and 'BrokenPromiseRecorded' not in ev(tx)
    skipped = ev(tx)['UpdateSkipped']
    assert [(e['user'], e['reason'], e['why']) for e in skipped] == [
        (alice, "PROMISE_FULFILLED:1", "ALREADY_PROCESSED"),
        (bob, "PROMISE_DEFAULTED:2", "ALREADY_PROCESSED"),
    ]
    assert updater.isProcessed(updater.updateKey(alice, "PROMISE_FULFILLED:1"))
    assert not updater.isProcessed(updater.updateKey(bob, "PROMISE_FULFILLED:1"))


def test_partially_new_batch_applies_only_the_new_updates(wired, updater_account, alice, bob):
    rep, updater = wired
    updater.applyReputationChanges([(alice, 25, "PROMISE_FULFILLED:1")], [], sender=updater_account)
    updater.applyReputationChanges(
        [(alice, 25, "PROMISE_FULFILLED:1"), (alice, 25, "PROMISE_FULFILLED:3"), (bob, 25, "PROMISE_FULFILLED:4")],
        [], sender=updater_account,
    )
    assert rep.reputationScores(alice) == 150 and rep.reputationScores(bob) == 125


def test_duplicate_within_one_batch_is_applied_once(wired, updater_account, alice):
    rep, updater = wired
    update = (alice, 25, "PROMISE_FULFILLED:1")
    updater.applyReputationChanges([update, update], [], sender=updater_account)
    assert rep.reputationScores(alice) == 125


def test_update_identity_is_user_and_reason_not_amount(wired, updater_account, alice, bob):
    rep, updater = wired
    updater.applyReputationChanges([(alice, 25, "X")], [], sender=updater_account)
    updater.applyReputationChanges([(alice, 999, "X"), (bob, 25, "X")], [], sender=updater_account)
    assert rep.reputationScores(alice) == 125  # same (user, reason): skipped whatever the amount
    assert rep.reputationScores(bob) == 125  # same reason, different user: a different update


def test_updater_applies_updates_whatever_the_users_delinquent_status(wired, updater_account, alice, bob):
    """Eligibility is the oracle's decision, made from the status when the promise was kept."""
    rep, updater = wired
    rep.setDelinquentStatus(alice, True, sender=accounts[8])
    batch = ([(alice, 25, "PROMISE_FULFILLED:1"), (bob, 25, "PROMISE_FULFILLED:2")], [(alice, 40, "PROMISE_DEFAULTED:3")])

    tx = updater.applyReputationChanges(*batch, sender=updater_account)

    assert rep.reputationScores(bob) == 125
    assert rep.reputationScores(alice) == 100 + 25
    assert rep.brokenScores(alice) == 40
    assert 'UpdateSkipped' not in ev(tx)
