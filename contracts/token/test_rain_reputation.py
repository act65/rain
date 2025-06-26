import pytest
from brownie import RainReputation, accounts, reverts # type: ignore

# --- Constants ---
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
UPDATER_ROLE_HASH = "0xabC123..." # Replace with actual keccak256("UPDATER_ROLE") if needed for raw checks
                                # Brownie handles this via contract.UPDATER_ROLE()

@pytest.fixture(scope="module")
def admin():
    return accounts[0]

@pytest.fixture(scope="module")
def updater_user(): # User who will be granted UPDATER_ROLE
    return accounts[1]

@pytest.fixture(scope="module")
def user_a():
    return accounts[2]

@pytest.fixture(scope="module")
def user_b():
    return accounts[3]

@pytest.fixture(scope="module")
def rct_mock_contract(): # Address for the mock RCT contract
    return accounts[4]

@pytest.fixture(scope="module")
def other_user():
    return accounts[5]


@pytest.fixture(scope="module")
def rain_reputation_contract(admin, updater_user):
    """Deploys the RainReputation contract and grants UPDATER_ROLE."""
    contract = admin.deploy(RainReputation)
    contract.grantRole(contract.UPDATER_ROLE(), updater_user, {"from": admin})
    # Note: rctContractAddress is not set initially.
    return contract

# --- Test Cases ---

def test_initial_state(rain_reputation_contract, admin, updater_user):
    assert rain_reputation_contract.name() == "Rain Reputation Token"
    assert rain_reputation_contract.symbol() == "RAIN"
    assert rain_reputation_contract.hasRole(rain_reputation_contract.DEFAULT_ADMIN_ROLE(), admin)
    assert rain_reputation_contract.hasRole(rain_reputation_contract.UPDATER_ROLE(), updater_user)
    assert rain_reputation_contract.totalReputation() == 0
    assert rain_reputation_contract.rctContractAddress() == ZERO_ADDRESS

def test_mint_sbt(rain_reputation_contract, admin, user_a):
    initial_rep = 1000
    tx = rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    token_id = tx.return_value # or tx.events["Transfer"]["tokenId"]
    assert rain_reputation_contract.ownerOf(token_id) == user_a
    assert rain_reputation_contract.balanceOf(user_a) == 1
    assert rain_reputation_contract.reputationScores(user_a) == initial_rep
    assert rain_reputation_contract.totalReputation() == initial_rep

    assert "Transfer" in tx.events # ERC721 mint event
    assert tx.events["Transfer"]["from"] == ZERO_ADDRESS
    assert tx.events["Transfer"]["to"] == user_a
    assert tx.events["Transfer"]["tokenId"] == token_id

def test_mint_sbt_not_admin(rain_reputation_contract, user_a, other_user):
    with reverts("Admin only"):
        rain_reputation_contract.mint(other_user, 100, {"from": user_a})

def test_sbt_non_transferable(rain_reputation_contract, admin, user_a, user_b):
    rain_reputation_contract.mint(user_a, 100, {"from": admin})
    token_id = rain_reputation_contract.tokenOfOwnerByIndex(user_a, 0)

    with reverts("RAIN: This token is non-transferable"):
        rain_reputation_contract.transferFrom(user_a, user_b, token_id, {"from": user_a})
    with reverts("RAIN: This token is non-transferable"):
        rain_reputation_contract.safeTransferFrom(user_a, user_b, token_id, {"from": user_a})

def test_increase_reputation(rain_reputation_contract, admin, updater_user, user_a):
    initial_rep = 500
    increase_amount = 200
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin}) # Mint SBT first

    initial_total_rep = rain_reputation_contract.totalReputation()

    tx = rain_reputation_contract.increaseReputation(user_a, increase_amount, "Good work", {"from": updater_user})

    assert rain_reputation_contract.reputationScores(user_a) == initial_rep + increase_amount
    assert rain_reputation_contract.totalReputation() == initial_total_rep + increase_amount
    assert "ReputationIncreased" in tx.events
    evt = tx.events["ReputationIncreased"]
    assert evt["user"] == user_a
    assert evt["amount"] == increase_amount
    assert evt["reason"] == "Good work"

def test_increase_reputation_not_updater(rain_reputation_contract, admin, user_a, other_user):
    rain_reputation_contract.mint(user_a, 100, {"from": admin})
    with reverts("Caller is not a trusted updater"):
        rain_reputation_contract.increaseReputation(user_a, 50, "Trying to cheat", {"from": other_user})

def test_decrease_reputation(rain_reputation_contract, admin, updater_user, user_a):
    initial_rep = 500
    decrease_amount = 150
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    initial_total_rep = rain_reputation_contract.totalReputation()

    tx = rain_reputation_contract.decreaseReputation(user_a, decrease_amount, "Minor issue", {"from": updater_user})

    assert rain_reputation_contract.reputationScores(user_a) == initial_rep - decrease_amount
    assert rain_reputation_contract.totalReputation() == initial_total_rep - decrease_amount
    assert "ReputationDecreased" in tx.events
    evt = tx.events["ReputationDecreased"]
    assert evt["user"] == user_a
    assert evt["amount"] == decrease_amount
    assert evt["reason"] == "Minor issue"

def test_decrease_reputation_to_zero(rain_reputation_contract, admin, updater_user, user_a):
    initial_rep = 100
    decrease_amount = 150 # More than current rep
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    initial_total_rep = rain_reputation_contract.totalReputation()

    tx = rain_reputation_contract.decreaseReputation(user_a, decrease_amount, "Large issue", {"from": updater_user})

    assert rain_reputation_contract.reputationScores(user_a) == 0
    # Total reputation decreases only by actual_decrease (initial_rep)
    assert rain_reputation_contract.totalReputation() == initial_total_rep - initial_rep
    assert tx.events["ReputationDecreased"]["amount"] == initial_rep # Actual decrease

def test_slash_reputation(rain_reputation_contract, admin, updater_user, user_a):
    initial_rep = 1000
    slash_amount = 300
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    initial_total_rep = rain_reputation_contract.totalReputation()

    tx = rain_reputation_contract.slash(user_a, slash_amount, {"from": updater_user})

    assert rain_reputation_contract.reputationScores(user_a) == initial_rep - slash_amount
    assert rain_reputation_contract.totalReputation() == initial_total_rep - slash_amount
    assert "ReputationSlashed" in tx.events
    evt = tx.events["ReputationSlashed"]
    assert evt["user"] == user_a
    assert evt["amount"] == slash_amount

def test_slash_reputation_more_than_exists(rain_reputation_contract, admin, updater_user, user_a):
    initial_rep = 200
    slash_amount = 300
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})
    initial_total_rep = rain_reputation_contract.totalReputation()

    tx = rain_reputation_contract.slash(user_a, slash_amount, {"from": updater_user})

    assert rain_reputation_contract.reputationScores(user_a) == 0
    assert rain_reputation_contract.totalReputation() == initial_total_rep - initial_rep # Slashed by actual rep
    assert tx.events["ReputationSlashed"]["amount"] == initial_rep


def test_stake_and_release_reputation(rain_reputation_contract, admin, user_a):
    initial_rep = 1000
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    stake_amount = 400
    purpose_id = b"test_purpose_123" # bytes32

    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep

    # Stake
    tx_stake = rain_reputation_contract.stake(user_a, stake_amount, purpose_id, {"from": user_a}) # User stakes for themselves

    assert rain_reputation_contract.reputationScores(user_a) == initial_rep # Total score unchanged
    assert rain_reputation_contract.stakedReputation(user_a) == stake_amount
    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep - stake_amount

    stake_info = rain_reputation_contract.stakes(purpose_id)
    assert stake_info["user"] == user_a
    assert stake_info["amount"] == stake_amount
    assert not stake_info["isReleased"]

    assert "ReputationStaked" in tx_stake.events
    evt_stake = tx_stake.events["ReputationStaked"]
    assert evt_stake["purposeId"] == purpose_id.hex() # Brownie converts bytes32 to hex string in events
    assert evt_stake["user"] == user_a
    assert evt_stake["amount"] == stake_amount

    # Release Stake
    # Typically, release might be called by a script or system, but here user_a calls for simplicity if allowed
    # The contract allows anyone to call releaseStake for an existing stake.
    tx_release = rain_reputation_contract.releaseStake(purpose_id, {"from": other_user}) # Anyone can call release

    assert rain_reputation_contract.stakedReputation(user_a) == 0
    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep

    stake_info_after_release = rain_reputation_contract.stakes(purpose_id)
    assert stake_info_after_release["isReleased"] # True

    assert "StakeReleased" in tx_release.events
    evt_release = tx_release.events["StakeReleased"]
    assert evt_release["purposeId"] == purpose_id.hex()
    assert evt_release["user"] == user_a
    assert evt_release["amount"] == stake_amount

def test_stake_insufficient_liquid_reputation(rain_reputation_contract, admin, user_a):
    initial_rep = 100
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    with reverts("Insufficient liquid reputation"):
        rain_reputation_contract.stake(user_a, initial_rep + 1, b"purpose1", {"from": user_a})

def test_stake_for_existing_purpose(rain_reputation_contract, admin, user_a):
    initial_rep = 200
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})
    purpose_id = b"duplicate_purpose"
    rain_reputation_contract.stake(user_a, 50, purpose_id, {"from": user_a})

    with reverts("Stake for this purpose already exists"):
        rain_reputation_contract.stake(user_a, 50, purpose_id, {"from": user_a})

def test_release_non_existent_stake(rain_reputation_contract):
    with reverts("Stake does not exist"):
        rain_reputation_contract.releaseStake(b"ghost_purpose", {"from": accounts[0]})

def test_release_already_released_stake(rain_reputation_contract, admin, user_a):
    rain_reputation_contract.mint(user_a, 100, {"from": admin})
    purpose_id = b"release_twice"
    rain_reputation_contract.stake(user_a, 50, purpose_id, {"from": user_a})
    rain_reputation_contract.releaseStake(purpose_id, {"from": user_a}) # First release

    with reverts("Stake already released"):
        rain_reputation_contract.releaseStake(purpose_id, {"from": user_a}) # Second release

def test_set_rct_contract_address(rain_reputation_contract, admin, rct_mock_contract):
    assert rain_reputation_contract.rctContractAddress() == ZERO_ADDRESS
    rain_reputation_contract.setRctContract(rct_mock_contract, {"from": admin})
    assert rain_reputation_contract.rctContractAddress() == rct_mock_contract

def test_set_rct_contract_address_not_admin(rain_reputation_contract, user_a, rct_mock_contract):
    with reverts("Admin only"):
        rain_reputation_contract.setRctContract(rct_mock_contract, {"from": user_a})

def test_set_rct_contract_address_already_set(rain_reputation_contract, admin, rct_mock_contract):
    rain_reputation_contract.setRctContract(rct_mock_contract, {"from": admin}) # First set
    new_rct_address = accounts[6]
    with reverts("RCT contract already set"):
        rain_reputation_contract.setRctContract(new_rct_address, {"from": admin}) # Attempt to set again

def test_set_delinquent_status(rain_reputation_contract, admin, user_a, rct_mock_contract):
    rain_reputation_contract.setRctContract(rct_mock_contract, {"from": admin}) # Allow rct_mock_contract to call

    assert not rain_reputation_contract.isDelinquent(user_a)

    # Set delinquent true
    tx_delinquent = rain_reputation_contract.setDelinquentStatus(user_a, True, {"from": rct_mock_contract})
    assert rain_reputation_contract.isDelinquent(user_a)
    assert "DelinquentStatusChanged" in tx_delinquent.events
    assert tx_delinquent.events["DelinquentStatusChanged"]["user"] == user_a
    assert tx_delinquent.events["DelinquentStatusChanged"]["isDelinquent"] == True

    # Set delinquent false
    tx_not_delinquent = rain_reputation_contract.setDelinquentStatus(user_a, False, {"from": rct_mock_contract})
    assert not rain_reputation_contract.isDelinquent(user_a)
    assert "DelinquentStatusChanged" in tx_not_delinquent.events
    assert tx_not_delinquent.events["DelinquentStatusChanged"]["isDelinquent"] == False

def test_set_delinquent_status_not_rct_contract(rain_reputation_contract, admin, user_a, other_user):
    # rctContractAddress is ZERO_ADDRESS initially, or set it to something specific
    # rain_reputation_contract.setRctContract(accounts[9], {"from": admin})

    # other_user is not the rct_mock_contract
    with reverts("Only the RCT contract can set delinquent status"):
        rain_reputation_contract.setDelinquentStatus(user_a, True, {"from": other_user})

def test_increase_reputation_when_delinquent(rain_reputation_contract, admin, updater_user, user_a, rct_mock_contract):
    initial_rep = 100
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})
    rain_reputation_contract.setRctContract(rct_mock_contract, {"from": admin})
    rain_reputation_contract.setDelinquentStatus(user_a, True, {"from": rct_mock_contract}) # User is now delinquent

    assert rain_reputation_contract.isDelinquent(user_a)

    with reverts("RainReputation: User is delinquent and cannot earn reputation"):
        rain_reputation_contract.increaseReputation(user_a, 50, "Trying to earn while delinquent", {"from": updater_user})

    # Score and total rep should remain unchanged
    assert rain_reputation_contract.reputationScores(user_a) == initial_rep
    # Total rep might need careful tracking if minting happened in this test vs fixture.
    # Assuming totalReputation was `initial_rep` after mint.
    assert rain_reputation_contract.totalReputation() == initial_rep # Or whatever it was before the failed increase

def test_get_liquid_reputation(rain_reputation_contract, admin, user_a):
    initial_rep = 1000
    stake_amount = 300
    rain_reputation_contract.mint(user_a, initial_rep, {"from": admin})

    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep

    rain_reputation_contract.stake(user_a, stake_amount, b"purpose_liquid", {"from": user_a})
    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep - stake_amount

    rain_reputation_contract.releaseStake(b"purpose_liquid", {"from": user_a})
    assert rain_reputation_contract.getLiquidReputation(user_a) == initial_rep

# Test AccessControl for roles (grantRole, revokeRole, renounceRole) can be added if needed for full coverage.
# The fixture already grants UPDATER_ROLE. Testing DEFAULT_ADMIN_ROLE for admin functions is implicitly done.
```
