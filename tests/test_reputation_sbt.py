import pytest
from brownie import ReputationSBT, accounts, reverts

@pytest.fixture
def reputation_sbt():
    # Deploy the contract before each test
    return ReputationSBT.deploy({'from': accounts[0]})

def test_initial_sbt_state(reputation_sbt):
    assert reputation_sbt.name() == "Reputation Token"
    assert reputation_sbt.symbol() == "REPSBT"

def test_award_reputation(reputation_sbt):
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100

    # Award reputation using the mint function
    tx = reputation_sbt.mint(user, initial_score, {'from': owner})

    # Token ID will be 1 as it's the first mint
    token_id = tx.events["Transfer"]["tokenId"]

    # Check ownership and score
    assert reputation_sbt.ownerOf(token_id) == user
    assert reputation_sbt.reputationScores(user) == initial_score
    assert reputation_sbt.balanceOf(user) == 1

    # Check event emission (ERC721 Transfer event)
    assert "Transfer" in tx.events
    assert tx.events["Transfer"]["from"] == "0x0000000000000000000000000000000000000000"
    assert tx.events["Transfer"]["to"] == user
    assert tx.events["Transfer"]["tokenId"] == token_id

def test_award_reputation_twice_updates_score_does_not_mint_new_sbt(reputation_sbt):
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100
    additional_score = 50
    expected_total_score = initial_score + additional_score

    # First award (mint)
    tx1 = reputation_sbt.mint(user, initial_score, {'from': owner})
    token_id = tx1.events["Transfer"]["tokenId"] # Get the token ID from the event
    assert reputation_sbt.ownerOf(token_id) == user
    assert reputation_sbt.reputationScores(user) == initial_score
    assert reputation_sbt.balanceOf(user) == 1

    # To update score, owner first needs to be a trusted contract
    reputation_sbt.setTrustedContract(owner, True, {'from': owner})
    # Then increase reputation
    tx2 = reputation_sbt.increaseReputation(user, additional_score, {'from': owner})

    # Score should be updated
    assert reputation_sbt.reputationScores(user) == expected_total_score
    # User should still only have one SBT. The contract's mint function would create a new token.
    # This test verifies that increaseReputation updates the score without minting a new token.
    assert reputation_sbt.balanceOf(user) == 1
    assert reputation_sbt.ownerOf(token_id) == user

    # The contract does not emit 'ReputationUpdated' event for increaseReputation.
    # No specific event to check here beyond the successful transaction.

def test_award_reputation_not_owner(reputation_sbt):
    non_owner = accounts[1]
    user = accounts[2]
    score = 100
    with reverts("Ownable: caller is not the owner"):
        reputation_sbt.mint(user, score, {'from': non_owner})

def test_sbt_non_transferable(reputation_sbt):
    owner = accounts[0]
    user1 = accounts[1]
    user2 = accounts[2]
    score = 100

    tx = reputation_sbt.mint(user1, score, {'from': owner})
    token_id = tx.events["Transfer"]["tokenId"]
    assert reputation_sbt.ownerOf(token_id) == user1

    # Attempt to transfer - should fail
    with reverts("SBT: This token is non-transferable"):
        reputation_sbt.transferFrom(user1, user2, token_id, {'from': user1})
    with reverts("SBT: This token is non-transferable"):
        reputation_sbt.safeTransferFrom(user1, user2, token_id, {'from': user1})

    # Ensure ownership hasn't changed
    assert reputation_sbt.ownerOf(token_id) == user1
    assert reputation_sbt.balanceOf(user1) == 1
    assert reputation_sbt.balanceOf(user2) == 0

def test_update_reputation_score_directly(reputation_sbt):
    owner = accounts[0]
    user = accounts[1]
    initial_score = 100
    score_increase = 50 # How much to increase the score by
    expected_score_after_increase = initial_score + score_increase

    tx_mint = reputation_sbt.mint(user, initial_score, {'from': owner})
    token_id = tx_mint.events["Transfer"]["tokenId"]
    assert reputation_sbt.reputationScores(user) == initial_score

    # Owner must be a trusted contract to update score
    reputation_sbt.setTrustedContract(owner, True, {'from': owner})

    # Update score by increasing
    tx_increase = reputation_sbt.increaseReputation(user, score_increase, {'from': owner})
    assert reputation_sbt.reputationScores(user) == expected_score_after_increase

    # The contract does not emit 'ReputationUpdated' event for increaseReputation.
    # No specific event to check here beyond the successful transaction.

    # Ensure token ownership and count remain
    assert reputation_sbt.ownerOf(token_id) == user
    assert reputation_sbt.balanceOf(user) == 1


def test_update_reputation_score_not_owner(reputation_sbt):
    owner = accounts[0]
    non_owner = accounts[1]
    user = accounts[2]
    initial_score = 100
    score_to_add = 50

    reputation_sbt.mint(user, initial_score, {'from': owner})
    # Non-owner is not a trusted contract by default
    with reverts("Caller is not a trusted contract"):
        reputation_sbt.increaseReputation(user, score_to_add, {'from': non_owner})

def test_award_to_zero_address(reputation_sbt):
    owner = accounts[0]
    zero_address = "0x0000000000000000000000000000000000000000"
    score = 100
    with reverts("ERC721: mint to the zero address"):
        reputation_sbt.mint(zero_address, score, {'from': owner})

def test_get_reputation_score_no_sbt(reputation_sbt):
    user_no_sbt = accounts[5]
    assert reputation_sbt.reputationScores(user_no_sbt) == 0
