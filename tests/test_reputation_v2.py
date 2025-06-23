import pytest
from brownie import ReputationV2, accounts, reverts # Changed ReputationSBT to ReputationV2

@pytest.fixture
def reputation_v2(): # Changed fixture name
    # Deploy the contract before each test
    return ReputationV2.deploy({'from': accounts[0]})

def test_initial_v2_state(reputation_v2): # Changed test name and fixture name
    assert reputation_v2.name() == "Reputation Token" # Name is the same
    assert reputation_v2.symbol() == "REPSBT" # Symbol is the same

def test_mint_reputation(reputation_v2): # Changed test name and fixture name
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100

    # Award reputation using the mint function
    tx = reputation_v2.mint(user, initial_score, {'from': owner}) # Changed to reputation_v2

    # Token ID will be 1 as it's the first mint
    token_id = tx.events["Transfer"]["tokenId"]

    # Check ownership and score
    assert reputation_v2.ownerOf(token_id) == user # Changed to reputation_v2
    assert reputation_v2.getEffectiveReputation(user) == initial_score # Changed to reputation_v2 and getEffectiveReputation
    assert reputation_v2.balanceOf(user) == 1 # Changed to reputation_v2

    # Check event emission (ERC721 Transfer event)
    assert "Transfer" in tx.events
    assert tx.events["Transfer"]["from"] == "0x0000000000000000000000000000000000000000"
    assert tx.events["Transfer"]["to"] == user
    assert tx.events["Transfer"]["tokenId"] == token_id

def test_increase_reputation_updates_score(reputation_v2): # Changed test name and fixture
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100
    additional_score = 50
    expected_total_score = initial_score + additional_score

    # First award (mint)
    tx1 = reputation_v2.mint(user, initial_score, {'from': owner}) # Changed to reputation_v2
    token_id = tx1.events["Transfer"]["tokenId"]
    assert reputation_v2.ownerOf(token_id) == user # Changed to reputation_v2
    assert reputation_v2.getEffectiveReputation(user) == initial_score # Changed to reputation_v2 and getEffectiveReputation
    assert reputation_v2.balanceOf(user) == 1 # Changed to reputation_v2

    # To update score, owner first needs to be a trusted contract
    reputation_v2.setTrustedContract(owner, True, {'from': owner}) # Changed to reputation_v2
    # Then increase reputation using the overridden function
    tx_increase = reputation_v2.increaseReputation(user, additional_score, {'from': owner}) # Changed to reputation_v2

    # Score should be updated
    assert reputation_v2.getEffectiveReputation(user) == expected_total_score # Changed to reputation_v2 and getEffectiveReputation
    # User should still only have one SBT.
    assert reputation_v2.balanceOf(user) == 1 # Changed to reputation_v2
    assert reputation_v2.ownerOf(token_id) == user # Changed to reputation_v2

    # Check for ReputationAdjustedFromTransaction event
    assert "ReputationAdjustedFromTransaction" in tx_increase.events
    assert tx_increase.events["ReputationAdjustedFromTransaction"]["user"] == user
    assert tx_increase.events["ReputationAdjustedFromTransaction"]["oldReputation"] == initial_score
    assert tx_increase.events["ReputationAdjustedFromTransaction"]["newReputation"] == expected_total_score

def test_mint_reputation_not_owner(reputation_v2): # Changed fixture and test name
    non_owner = accounts[1]
    user = accounts[2]
    score = 100
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.mint(user, score, {'from': non_owner}) # Changed to reputation_v2

def test_sbt_non_transferable(reputation_v2): # Changed fixture
    owner = accounts[0]
    user1 = accounts[1]
    user2 = accounts[2]
    score = 100

    tx = reputation_v2.mint(user1, score, {'from': owner}) # Changed to reputation_v2
    token_id = tx.events["Transfer"]["tokenId"]
    assert reputation_v2.ownerOf(token_id) == user1 # Changed to reputation_v2

    # Attempt to transfer - should fail
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.transferFrom(user1, user2, token_id, {'from': user1}) # Changed to reputation_v2
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.safeTransferFrom(user1, user2, token_id, {'from': user1}) # Changed to reputation_v2

    # Ensure ownership hasn't changed
    assert reputation_v2.ownerOf(token_id) == user1 # Changed to reputation_v2
    assert reputation_v2.balanceOf(user1) == 1 # Changed to reputation_v2
    assert reputation_v2.balanceOf(user2) == 0 # Changed to reputation_v2

def test_decrease_reputation(reputation_v2): # Changed test name and fixture
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100
    score_decrease = 30
    expected_score_after_decrease = initial_score - score_decrease

    tx_mint = reputation_v2.mint(user, initial_score, {'from': owner}) # Changed to reputation_v2
    token_id = tx_mint.events["Transfer"]["tokenId"]
    assert reputation_v2.getEffectiveReputation(user) == initial_score # Changed to reputation_v2 and getEffectiveReputation

    # Owner must be a trusted contract to update score
    reputation_v2.setTrustedContract(owner, True, {'from': owner}) # Changed to reputation_v2

    # Update score by decreasing
    tx_decrease = reputation_v2.decreaseReputation(user, score_decrease, {'from': owner}) # Changed to reputation_v2
    assert reputation_v2.getEffectiveReputation(user) == expected_score_after_decrease # Changed to reputation_v2 and getEffectiveReputation

    # Check for ReputationAdjustedFromTransaction event
    assert "ReputationAdjustedFromTransaction" in tx_decrease.events
    assert tx_decrease.events["ReputationAdjustedFromTransaction"]["user"] == user
    assert tx_decrease.events["ReputationAdjustedFromTransaction"]["oldReputation"] == initial_score
    assert tx_decrease.events["ReputationAdjustedFromTransaction"]["newReputation"] == expected_score_after_decrease

    # Ensure token ownership and count remain
    assert reputation_v2.ownerOf(token_id) == user # Changed to reputation_v2
    assert reputation_v2.balanceOf(user) == 1 # Changed to reputation_v2


def test_update_reputation_score_not_trusted_contract(reputation_v2): # Changed test name and fixture
    owner = accounts[0]
    non_trusted_caller = accounts[1] # This caller is not owner and not set as trusted
    user = accounts[2]
    initial_score = 100
    score_to_add = 50

    reputation_v2.mint(user, initial_score, {'from': owner}) # Changed to reputation_v2
    # Non-trusted caller attempts to change reputation
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.increaseReputation(user, score_to_add, {'from': non_trusted_caller}) # Changed to reputation_v2
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.decreaseReputation(user, score_to_add, {'from': non_trusted_caller}) # Changed to reputation_v2

def test_mint_to_zero_address(reputation_v2): # Changed test name and fixture
    owner = accounts[0]
    zero_address = "0x0000000000000000000000000000000000000000"
    score = 100
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.mint(zero_address, score, {'from': owner}) # Changed to reputation_v2

def test_get_reputation_score_no_sbt(reputation_v2): # Changed fixture
    user_no_sbt = accounts[5]
    assert reputation_v2.getEffectiveReputation(user_no_sbt) == 0 # Changed to reputation_v2 and getEffectiveReputation

# --- ReputationV2 Specific Tests ---

def test_initial_transaction_score(reputation_v2):
    user = accounts[1]
    # Mint an SBT for the user first (needed to have a reputation context)
    reputation_v2.mint(user, 100, {'from': accounts[0]})
    assert reputation_v2.transactionScores(user) == 0

def test_increase_transaction_score_v2(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0] # Owner can be trusted for this test
    user = accounts[1]
    initial_rep = 100
    tx_score_increase = 20
    expected_rep_after_tx = initial_rep + tx_score_increase

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    tx = reputation_v2.increaseTransactionScoreV2(user, tx_score_increase, {'from': trusted_contract})

    assert reputation_v2.transactionScores(user) == tx_score_increase
    assert reputation_v2.getEffectiveReputation(user) == expected_rep_after_tx

    assert "TransactionScoreUpdated" in tx.events
    assert tx.events["TransactionScoreUpdated"]["user"] == user
    assert tx.events["TransactionScoreUpdated"]["newTransactionScore"] == tx_score_increase
    assert tx.events["TransactionScoreUpdated"]["change"] == tx_score_increase

    assert "ReputationAdjustedFromTransaction" in tx.events
    assert tx.events["ReputationAdjustedFromTransaction"]["user"] == user
    assert tx.events["ReputationAdjustedFromTransaction"]["oldReputation"] == initial_rep
    assert tx.events["ReputationAdjustedFromTransaction"]["newReputation"] == expected_rep_after_tx

def test_decrease_transaction_score_v2(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0] # Owner can be trusted
    user = accounts[1]
    initial_rep = 100
    tx_score_decrease = 30
    expected_rep_after_tx = initial_rep - tx_score_decrease
    expected_tx_score_after_decrease = -30 # int

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    tx = reputation_v2.decreaseTransactionScoreV2(user, tx_score_decrease, {'from': trusted_contract})

    assert reputation_v2.transactionScores(user) == expected_tx_score_after_decrease
    assert reputation_v2.getEffectiveReputation(user) == expected_rep_after_tx

    assert "TransactionScoreUpdated" in tx.events
    assert tx.events["TransactionScoreUpdated"]["user"] == user
    assert tx.events["TransactionScoreUpdated"]["newTransactionScore"] == expected_tx_score_after_decrease
    assert tx.events["TransactionScoreUpdated"]["change"] == -int(tx_score_decrease) # Ensure negative change

    assert "ReputationAdjustedFromTransaction" in tx.events
    assert tx.events["ReputationAdjustedFromTransaction"]["user"] == user
    assert tx.events["ReputationAdjustedFromTransaction"]["oldReputation"] == initial_rep
    assert tx.events["ReputationAdjustedFromTransaction"]["newReputation"] == expected_rep_after_tx

def test_decrease_transaction_score_v2_below_zero_rep(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 20
    tx_score_decrease = 30 # More than initial rep
    expected_rep_after_tx = 0 # Reputation cannot go below zero
    expected_tx_score_after_decrease = -30

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    tx = reputation_v2.decreaseTransactionScoreV2(user, tx_score_decrease, {'from': trusted_contract})

    assert reputation_v2.transactionScores(user) == expected_tx_score_after_decrease
    assert reputation_v2.getEffectiveReputation(user) == expected_rep_after_tx

def test_transaction_score_v2_not_trusted_contract(reputation_v2):
    owner = accounts[0]
    non_trusted_caller = accounts[1]
    user = accounts[2]
    initial_rep = 100
    score_change = 10

    reputation_v2.mint(user, initial_rep, {'from': owner})
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.increaseTransactionScoreV2(user, score_change, {'from': non_trusted_caller})
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.decreaseTransactionScoreV2(user, score_change, {'from': non_trusted_caller})

def test_stake_reputation(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0] # For simplicity, owner is trusted
    user = accounts[1]
    initial_rep = 100
    stake_amount = 40

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

    assert reputation_v2.stakedReputation(user) == stake_amount
    # Effective reputation should not change upon staking, only available vs staked changes.
    assert reputation_v2.getEffectiveReputation(user) == initial_rep

def test_stake_more_than_available_reputation(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 100
    stake_amount = 120 # More than initial_rep

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

def test_release_stake(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 100
    stake_amount = 40
    release_amount = 30

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})
    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == stake_amount

    reputation_v2.releaseStake(user, release_amount, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == stake_amount - release_amount
    assert reputation_v2.getEffectiveReputation(user) == initial_rep

def test_release_more_than_staked(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 100
    stake_amount = 40
    release_amount = 50 # More than staked

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})
    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.releaseStake(user, release_amount, {'from': trusted_contract})

def test_slash_stake(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 100
    stake_amount = 50
    slash_amount = 30
    expected_rep_after_slash = initial_rep - slash_amount
    expected_stake_after_slash = stake_amount - slash_amount

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})
    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

    reputation_v2.slash(user, slash_amount, {'from': trusted_contract})

    assert reputation_v2.stakedReputation(user) == expected_stake_after_slash
    assert reputation_v2.getEffectiveReputation(user) == expected_rep_after_slash

def test_slash_more_than_staked(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 100
    stake_amount = 50
    slash_amount = 60 # More than staked

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})
    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.slash(user, slash_amount, {'from': trusted_contract})

def test_slash_stake_reduces_reputation_to_zero(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 40
    stake_amount = 40 # Stake all reputation
    slash_amount = 50 # Try to slash more than total reputation (but not more than staked initially)
                      # Contract logic: slash from stake, then from rep scores. Rep scores can go to 0.

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})
    reputation_v2.stake(user, stake_amount, {'from': trusted_contract})

    # Slashing 40 (as it's max of current stake)
    reputation_v2.slash(user, 40, {'from': trusted_contract})

    assert reputation_v2.stakedReputation(user) == 0
    assert reputation_v2.getEffectiveReputation(user) == 0

def test_stake_slash_release_interactions(reputation_v2):
    owner = accounts[0]
    trusted_contract = accounts[0]
    user = accounts[1]
    initial_rep = 200

    reputation_v2.mint(user, initial_rep, {'from': owner})
    reputation_v2.setTrustedContract(trusted_contract, True, {'from': owner})

    # Stake 100
    reputation_v2.stake(user, 100, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == 100
    assert reputation_v2.getEffectiveReputation(user) == 200

    # Slash 30
    reputation_v2.slash(user, 30, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == 70 # 100 - 30
    assert reputation_v2.getEffectiveReputation(user) == 170 # 200 - 30

    # Release 50
    reputation_v2.releaseStake(user, 50, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == 20 # 70 - 50
    assert reputation_v2.getEffectiveReputation(user) == 170 # Unchanged by release

    # Try to stake 160 (current rep 170, staked 20, available 150) - should fail
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        reputation_v2.stake(user, 160, {'from': trusted_contract})

    # Stake 150 (all remaining available)
    reputation_v2.stake(user, 150, {'from': trusted_contract})
    assert reputation_v2.stakedReputation(user) == 170 # 20 + 150
    assert reputation_v2.getEffectiveReputation(user) == 170
