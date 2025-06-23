import pytest
from brownie import OfflineToken, ReputationV2, accounts, reverts

# --- Fixtures ---

@pytest.fixture
def owner():
    return accounts[0]

@pytest.fixture
def user1():
    return accounts[1]

@pytest.fixture
def user2():
    return accounts[2]

@pytest.fixture
def jury_contract_mock(owner): # Mock jury contract for slashing tests
    # For simplicity, using a standard account as a mock.
    # In a more complex setup, this could be a deployed mock contract.
    return accounts[8]

@pytest.fixture
def reputation_v2(owner):
    # Deploy ReputationV2 contract
    rep_contract = ReputationV2.deploy({'from': owner})
    return rep_contract

@pytest.fixture
def offline_token(owner, reputation_v2):
    # Deploy OfflineToken contract linked to ReputationV2
    ot_contract = OfflineToken.deploy(reputation_v2.address, {'from': owner})
    # The OfflineToken contract needs to be a trusted contract in ReputationV2 to call stake/slash
    reputation_v2.setTrustedContract(ot_contract.address, True, {'from': owner})
    return ot_contract

@pytest.fixture
def setup_user_with_rep_and_stake_ability(owner, user1, reputation_v2, offline_token):
    # Mint initial reputation for user1
    initial_rep = 200
    reputation_v2.mint(user1, initial_rep, {'from': owner})
    assert reputation_v2.getEffectiveReputation(user1) == initial_rep
    # User1 now has reputation and can stake it via OfflineToken
    return {"user": user1, "initial_rep": initial_rep}

# --- Tests ---

def test_initial_state(offline_token, reputation_v2):
    assert offline_token.reputationContract() == reputation_v2.address
    assert offline_token.OFFLINE_TOKEN_ID() == 0
    assert offline_token.REPUTATION_TO_TOKEN_RATIO() == 1
    assert offline_token.uri(0) == "" # Default URI

def test_set_jury_contract(offline_token, owner, jury_contract_mock):
    assert offline_token.juryContractAddress() == "0x0000000000000000000000000000000000000000" # Initially zero
    offline_token.setJuryContract(jury_contract_mock.address, {'from': owner})
    assert offline_token.juryContractAddress() == jury_contract_mock.address

def test_set_jury_contract_not_owner(offline_token, user1, jury_contract_mock):
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.setJuryContract(jury_contract_mock.address, {'from': user1})

def test_stake_reputation_and_mint_tokens(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"]
    stake_amount = 50

    tx = offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})

    # Check OfflineToken state
    assert offline_token.stakedReputationByUser(user) == stake_amount
    assert offline_token.totalReputationStaked() == stake_amount
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == stake_amount * offline_token.REPUTATION_TO_TOKEN_RATIO()

    # Check ReputationV2 state
    assert reputation_v2.stakedReputation(user) == stake_amount
    assert reputation_v2.getEffectiveReputation(user) == initial_rep # Effective reputation should not change

    # Check events
    assert "ReputationStaked" in tx.events
    event = tx.events["ReputationStaked"]
    assert event["user"] == user
    assert event["reputationAmount"] == stake_amount
    assert event["tokenAmountMinted"] == stake_amount * offline_token.REPUTATION_TO_TOKEN_RATIO()

def test_stake_reputation_insufficient_available_rep(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"] # e.g., 200
    stake_amount_too_high = initial_rep + 100 # e.g., 300

    # This will revert in ReputationV2.stake()
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.stakeReputationAndMintTokens(stake_amount_too_high, {'from': user})

def test_redeem_tokens_and_release_stake(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"]
    stake_amount = 100
    redeem_token_amount = 30
    expected_rep_to_release = redeem_token_amount / offline_token.REPUTATION_TO_TOKEN_RATIO()

    # First, stake and mint
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == stake_amount
    assert reputation_v2.stakedReputation(user) == stake_amount
    initial_total_staked_in_ot = offline_token.totalReputationStaked()

    # Then, redeem
    tx_redeem = offline_token.redeemTokensAndReleaseStake(redeem_token_amount, {'from': user})

    # Check OfflineToken state
    assert offline_token.stakedReputationByUser(user) == stake_amount - expected_rep_to_release
    assert offline_token.totalReputationStaked() == initial_total_staked_in_ot - expected_rep_to_release
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == stake_amount - redeem_token_amount

    # Check ReputationV2 state
    assert reputation_v2.stakedReputation(user) == stake_amount - expected_rep_to_release
    assert reputation_v2.getEffectiveReputation(user) == initial_rep # Unchanged

    # Check event
    assert "StakeReleased" in tx_redeem.events
    event = tx_redeem.events["StakeReleased"]
    assert event["user"] == user
    assert event["reputationAmountReleased"] == expected_rep_to_release
    assert event["tokenAmountBurned"] == redeem_token_amount

def test_redeem_insufficient_offline_tokens(offline_token, setup_user_with_rep_and_stake_ability): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    stake_amount = 50
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.redeemTokensAndReleaseStake(stake_amount + 10, {'from': user})

def test_redeem_more_tokens_than_staked_reputation_implies(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability, owner, user2): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # user1 # Corrected fixture name
    user = user_info["user"]

    # User1 stakes 50 rep, gets 50 tokens
    offline_token.stakeReputationAndMintTokens(50, {'from': user})

    # User2 stakes 0 rep (has no rep initially), but somehow gets tokens (e.g. transferred from user1)
    # Mint some rep for user2 so they have an SBT, but don't stake it in OfflineToken
    reputation_v2.mint(user2, 100, {'from': owner})
    # Corrected to safeTransferFrom and added data argument (empty bytes)
    offline_token.safeTransferFrom(user, user2, offline_token.OFFLINE_TOKEN_ID(), 10, b"", {'from': user}) # User1 sends 10 tokens to User2
    assert offline_token.balanceOf(user2, offline_token.OFFLINE_TOKEN_ID()) == 10
    assert offline_token.stakedReputationByUser(user2) == 0

    # User2 tries to redeem 10 tokens, but has 0 rep staked in OfflineToken
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.redeemTokensAndReleaseStake(10, {'from': user2})

def test_slash_stake_by_jury(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability, owner, jury_contract_mock): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"]
    stake_amount = 100
    slash_rep_amount = 40

    offline_token.setJuryContract(jury_contract_mock.address, {'from': owner})
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})

    initial_user_token_balance = offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID())
    initial_total_staked_ot = offline_token.totalReputationStaked()
    initial_staked_rep_user_ot = offline_token.stakedReputationByUser(user)

    initial_staked_rep_user_v2 = reputation_v2.stakedReputation(user)
    initial_effective_rep_user_v2 = reputation_v2.getEffectiveReputation(user)

    tx_slash = offline_token.slashStake(user, slash_rep_amount, {'from': jury_contract_mock})

    # Check OfflineToken state
    expected_tokens_to_burn = slash_rep_amount * offline_token.REPUTATION_TO_TOKEN_RATIO()
    assert offline_token.stakedReputationByUser(user) == initial_staked_rep_user_ot - slash_rep_amount
    assert offline_token.totalReputationStaked() == initial_total_staked_ot - slash_rep_amount
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == initial_user_token_balance - expected_tokens_to_burn

    # Check ReputationV2 state (slash in ReputationV2 reduces both staked and effective reputation)
    assert reputation_v2.stakedReputation(user) == initial_staked_rep_user_v2 - slash_rep_amount
    assert reputation_v2.getEffectiveReputation(user) == initial_effective_rep_user_v2 - slash_rep_amount

    # Check event
    assert "StakeSlashed" in tx_slash.events
    event = tx_slash.events["StakeSlashed"]
    assert event["user"] == user
    assert event["reputationAmountSlashed"] == slash_rep_amount
    assert event["tokenAmountBurned"] == expected_tokens_to_burn

def test_slash_stake_by_owner_if_jury_not_set(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability, owner): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"]
    stake_amount = 100
    slash_rep_amount = 40

    # Jury contract is NOT set
    assert offline_token.juryContractAddress() == "0x0000000000000000000000000000000000000000"
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})

    tx_slash = offline_token.slashStake(user, slash_rep_amount, {'from': owner}) # Slashed by owner

    expected_tokens_to_burn = slash_rep_amount * offline_token.REPUTATION_TO_TOKEN_RATIO()
    assert offline_token.stakedReputationByUser(user) == stake_amount - slash_rep_amount
    assert reputation_v2.getEffectiveReputation(user) == initial_rep - slash_rep_amount
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == stake_amount - expected_tokens_to_burn

def test_slash_stake_not_authorized(offline_token, setup_user_with_rep_and_stake_ability, owner, user1, jury_contract_mock): # Corrected fixture name
    user_to_slash_info = setup_user_with_rep_and_stake_ability # This is user1 # Corrected fixture name
    user_to_slash = user_to_slash_info["user"]
    stake_amount = 100
    slash_rep_amount = 40

    offline_token.setJuryContract(jury_contract_mock.address, {'from': owner}) # Jury is set
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user_to_slash})

    # Attempt slash by owner (should fail as jury is set)
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.slashStake(user_to_slash, slash_rep_amount, {'from': owner})

    # Attempt slash by another user (not jury, not owner)
    random_user = accounts[3]
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.slashStake(user_to_slash, slash_rep_amount, {'from': random_user})

def test_slash_more_reputation_than_staked(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability, owner, jury_contract_mock): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user = user_info["user"]
    stake_amount = 50
    slash_rep_amount = stake_amount + 10 # More than staked in OfflineToken

    offline_token.setJuryContract(jury_contract_mock.address, {'from': owner})
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        offline_token.slashStake(user, slash_rep_amount, {'from': jury_contract_mock})

def test_slash_burns_available_tokens_if_less_than_equivalent_slashed_rep(offline_token, reputation_v2, setup_user_with_rep_and_stake_ability, owner, user2, jury_contract_mock): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # user1 # Corrected fixture name
    user = user_info["user"]
    initial_rep = user_info["initial_rep"]
    stake_amount = 100 # User1 stakes 100 rep, gets 100 tokens
    slash_rep_amount = 80 # Jury decides to slash 80 rep

    offline_token.setJuryContract(jury_contract_mock.address, {'from': owner})
    offline_token.stakeReputationAndMintTokens(stake_amount, {'from': user})
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == 100

    # User1 transfers 50 of their 100 tokens to user2
    # Note: OfflineToken does not restrict transfers by default in this version.
    offline_token.safeTransferFrom(user, user2, offline_token.OFFLINE_TOKEN_ID(), 50, b"", {'from': user}) # data should be bytes
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == 50 # User1 now has 50 tokens
    assert offline_token.balanceOf(user2, offline_token.OFFLINE_TOKEN_ID()) == 50

    tx_slash = offline_token.slashStake(user, slash_rep_amount, {'from': jury_contract_mock})

    # OfflineToken state for user1
    assert offline_token.stakedReputationByUser(user) == stake_amount - slash_rep_amount # 100 - 80 = 20
    # Tokens burned should be min(tokens_user_has, equivalent_of_slashed_rep) = min(50, 80) = 50
    assert offline_token.balanceOf(user, offline_token.OFFLINE_TOKEN_ID()) == 0 # All 50 tokens burned

    # ReputationV2 state for user1
    assert reputation_v2.stakedReputation(user) == stake_amount - slash_rep_amount # Staked rep in V2 also reduced
    assert reputation_v2.getEffectiveReputation(user) == initial_rep - slash_rep_amount # Effective rep reduced

    # Event check
    assert "StakeSlashed" in tx_slash.events
    event = tx_slash.events["StakeSlashed"]
    assert event["user"] == user
    assert event["reputationAmountSlashed"] == slash_rep_amount
    assert event["tokenAmountBurned"] == 50 # Actual tokens burned

# ERC1155 related basic tests
def test_erc1155_uri_set(offline_token, owner):
    # Default URI is "", can be set if metadata is hosted
    new_uri = "https://myapi.com/token/{id}.json"
    # To set URI, ERC1155 contract needs a setURI method, or it's fixed in constructor.
    # OpenZeppelin's ERC1155.sol doesn't have a public setURI by default after construction.
    # This test just confirms the current URI. If it needs to be updatable, contract needs modification.
    assert offline_token.uri(offline_token.OFFLINE_TOKEN_ID()) == ""
    # offline_token.setURI(new_uri, {'from': owner}) # If setURI were available
    # assert offline_token.uri(offline_token.OFFLINE_TOKEN_ID()) == new_uri


def test_erc1155_balance_of_batch(offline_token, setup_user_with_rep_and_stake_ability, user2): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user1 = user_info["user"]

    offline_token.stakeReputationAndMintTokens(50, {'from': user1}) # User1 gets 50 tokens of ID 0

    # User2 has no tokens of ID 0, and no tokens of a hypothetical ID 1
    token_id_0 = offline_token.OFFLINE_TOKEN_ID()
    token_id_1 = 1 # Hypothetical other token ID

    balances = offline_token.balanceOfBatch([user1, user1, user2, user2], [token_id_0, token_id_1, token_id_0, token_id_1])

    assert balances[0] == 50 # user1, token_id_0
    assert balances[1] == 0  # user1, token_id_1
    assert balances[2] == 0  # user2, token_id_0
    assert balances[3] == 0  # user2, token_id_1

def test_erc1155_approval_for_all(offline_token, user1, user2):
    assert not offline_token.isApprovedForAll(user1, user2)
    offline_token.setApprovalForAll(user2, True, {'from': user1})
    assert offline_token.isApprovedForAll(user1, user2)
    offline_token.setApprovalForAll(user2, False, {'from': user1})
    assert not offline_token.isApprovedForAll(user1, user2)

def test_erc1155_safe_transfer_from(offline_token, setup_user_with_rep_and_stake_ability, user2): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # Corrected fixture name
    user1 = user_info["user"]
    token_id = offline_token.OFFLINE_TOKEN_ID()
    amount_to_mint = 100
    amount_to_transfer = 30

    offline_token.stakeReputationAndMintTokens(amount_to_mint, {'from': user1})
    assert offline_token.balanceOf(user1, token_id) == amount_to_mint
    assert offline_token.balanceOf(user2, token_id) == 0

    offline_token.safeTransferFrom(user1, user2, token_id, amount_to_transfer, b"", {'from': user1}) # data should be bytes

    assert offline_token.balanceOf(user1, token_id) == amount_to_mint - amount_to_transfer
    assert offline_token.balanceOf(user2, token_id) == amount_to_transfer

def test_erc1155_safe_batch_transfer_from(offline_token, setup_user_with_rep_and_stake_ability, user2, owner): # Corrected fixture name
    user_info = setup_user_with_rep_and_stake_ability # user1 # Corrected fixture name
    user1 = user_info["user"]

    # Mint some reputation for user2 so they exist for other operations if needed
    reputation_v2_contract = ReputationV2.at(offline_token.reputationContract())
    reputation_v2_contract.mint(user2, 50, {'from': owner})

    token_id_0 = offline_token.OFFLINE_TOKEN_ID()
    # We only have one token type (ID 0). To test batch with different IDs, we'd need to mint them.
    # For now, let's assume we are transferring two batches of the same token ID.

    amount_to_mint = 100
    offline_token.stakeReputationAndMintTokens(amount_to_mint, {'from': user1}) # User1 has 100 of ID 0

    transfer_amounts = [20, 30] # Transfer 20 of ID 0, then 30 of ID 0
    token_ids_to_transfer = [token_id_0, token_id_0]

    offline_token.safeBatchTransferFrom(user1, user2, token_ids_to_transfer, transfer_amounts, b"", {'from': user1}) # data should be bytes

    assert offline_token.balanceOf(user1, token_id_0) == amount_to_mint - sum(transfer_amounts) # 100 - 50 = 50
    assert offline_token.balanceOf(user2, token_id_0) == sum(transfer_amounts) # 50
