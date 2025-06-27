import pytest
from brownie import RainReputation, ReputationClaimToken, accounts, reverts

# This fixture sets up the entire environment needed for the tests.
# It deploys both contracts, links them, and assigns necessary roles.
@pytest.fixture
def contracts():
    """
    Deploys and links RainReputation and ReputationClaimToken contracts.
    - Returns: A tuple of (reputation_contract, rct_contract)
    - Roles:
        - accounts[0] (admin) is the admin for both contracts.
        - accounts[1] (minter) is granted MINTER_ROLE on the RCT contract.
    """
    admin = accounts[0]
    minter = accounts[1]

    # 1. Deploy the RainReputation contract
    reputation_contract = RainReputation.deploy({'from': admin})

    # 2. Deploy the ReputationClaimToken contract, passing the reputation contract's address
    rct_contract = ReputationClaimToken.deploy(reputation_contract.address, {'from': admin})

    # 3. Link the reputation contract to the RCT contract so it can accept status changes
    reputation_contract.setRctContract(rct_contract.address, {'from': admin})

    # 4. Grant the MINTER_ROLE to our designated minter account
    minter_role = rct_contract.MINTER_ROLE()
    rct_contract.grantRole(minter_role, minter, {'from': admin})

    return reputation_contract, rct_contract


def test_deployment_and_setup(contracts):
    """
    Tests that the contracts are deployed and configured correctly.
    """
    reputation_contract, rct_contract = contracts
    admin = accounts[0]
    minter = accounts[1]

    # Check ERC721 properties
    assert rct_contract.name() == "Rain Reputation Claim"
    assert rct_contract.symbol() == "RCT"

    # Check that the reputation contract address was set correctly
    assert rct_contract.rainReputation() == reputation_contract.address

    # Check that the MINTER_ROLE was granted correctly
    minter_role = rct_contract.MINTER_ROLE()
    assert rct_contract.hasRole(minter_role, minter) == True
    assert rct_contract.hasRole(minter_role, admin) == False


def test_mint_permissions(contracts):
    """
    Ensures only an account with MINTER_ROLE can mint an RCT.
    """
    _, rct_contract = contracts
    unauthorized = accounts[2]
    defaulter = accounts[3]
    lender = accounts[4]

    # Attempt to mint from an unauthorized account
    with reverts("RCT: Caller is not a minter"):
        rct_contract.mint(123, defaulter, lender, 1000, accounts[5], {'from': unauthorized})


def test_mint_first_offense_and_delinquency(contracts):
    """
    Tests minting an RCT for a user's first default, which should make them delinquent.
    """
    reputation_contract, rct_contract = contracts
    minter = accounts[1]
    defaulter = accounts[3]
    lender = accounts[4]
    loan_contract = accounts[5]
    promise_id = 101
    shortfall = 5000

    # Pre-condition: Defaulter is not delinquent
    assert reputation_contract.isDelinquent(defaulter) == False

    # Act: Minter mints the first RCT against the defaulter
    tx = rct_contract.mint(promise_id, defaulter, lender, shortfall, loan_contract, {'from': minter})
    token_id = tx.return_value

    # Assert: Check state changes
    assert rct_contract.ownerOf(token_id) == lender
    assert rct_contract.debtCount(defaulter) == 1
    
    # Assert: Defaulter should now be delinquent
    assert reputation_contract.isDelinquent(defaulter) == True

    # Assert: Check claim details
    claim = rct_contract.claims(token_id)
    assert claim['promiseId'] == promise_id
    assert claim['defaulterAddress'] == defaulter
    assert claim['originalLenderAddress'] == lender
    assert claim['shortfallAmount'] == shortfall

    # Assert: Event was emitted correctly
    assert 'ClaimMinted' in tx.events
    assert tx.events['ClaimMinted']['tokenId'] == token_id
    assert tx.events['ClaimMinted']['defaulter'] == defaulter


def test_mint_subsequent_offense(contracts):
    """
    Tests that a second offense increments the debt count but doesn't re-trigger delinquency.
    """
    reputation_contract, rct_contract = contracts
    minter = accounts[1]
    defaulter = accounts[3]
    lender = accounts[4]

    # Arrange: Mint the first RCT
    rct_contract.mint(101, defaulter, lender, 5000, accounts[5], {'from': minter})
    assert rct_contract.debtCount(defaulter) == 1
    assert reputation_contract.isDelinquent(defaulter) == True

    # Act: Mint a second RCT against the same defaulter
    rct_contract.mint(102, defaulter, lender, 2000, accounts[6], {'from': minter})

    # Assert: Debt count is now 2, and delinquent status is still true
    assert rct_contract.debtCount(defaulter) == 2
    assert reputation_contract.isDelinquent(defaulter) == True


def test_burn_permissions_by_unapproved_non_owner(contracts):
    """
    Ensures an unapproved, non-owner account cannot burn the RCT.
    """
    _, rct_contract = contracts
    minter = accounts[1]
    defaulter = accounts[3]
    lender = accounts[4]

    # Arrange: Mint a token, which is owned by the lender
    tx = rct_contract.mint(201, defaulter, lender, 1000, accounts[5], {'from': minter})
    token_id = tx.return_value

    # Act & Assert: The defaulter (not the owner or approved) cannot burn it
    with reverts("ERC721: burn caller is not owner nor approved"):
        rct_contract.burn(token_id, {'from': defaulter})

    # Act & Assert: A random account cannot burn it
    with reverts("ERC721: burn caller is not owner nor approved"):
        rct_contract.burn(token_id, {'from': accounts[9]})


def test_burn_by_approved_address(contracts):
    """
    Tests that a non-owner who has been approved can burn the token.
    This simulates the LoanScript workflow.
    """
    reputation_contract, rct_contract = contracts
    minter = accounts[1]
    owner = accounts[3]  # This account will own the token
    approved_burner = accounts[4] # This account will be approved to burn it
    defaulter_address = accounts[5] # The address of the defaulter recorded in the token

    # 1. Mint a token. The 'owner' now holds it.
    tx = rct_contract.mint(501, defaulter_address, owner, 1000, accounts[6], {'from': minter})
    token_id = tx.return_value
    assert rct_contract.ownerOf(token_id) == owner

    # 2. The owner approves 'approved_burner' to manage this specific token
    rct_contract.approve(approved_burner, token_id, {'from': owner})
    assert rct_contract.getApproved(token_id) == approved_burner

    # 3. The 'approved_burner' (who is not the owner) successfully burns the token
    burn_tx = rct_contract.burn(token_id, {'from': approved_burner})

    # Assert: Token is gone
    with reverts("ERC721: invalid token ID"):
        rct_contract.ownerOf(token_id)

    # Assert: Event was emitted correctly
    assert 'ClaimBurned' in burn_tx.events
    assert burn_tx.events['ClaimBurned']['burner'] == approved_burner


def test_full_lifecycle_reacquire_and_burn(contracts):
    """
    Tests the complete cycle:
    1. Mint RCT -> Lender owns it, Defaulter is delinquent.
    2. Lender transfers RCT to Defaulter.
    3. Defaulter burns RCT -> Defaulter is no longer delinquent.
    """
    reputation_contract, rct_contract = contracts
    minter = accounts[1]
    defaulter = accounts[3]
    lender = accounts[4]

    # 1. Mint RCT
    tx = rct_contract.mint(301, defaulter, lender, 1000, accounts[5], {'from': minter})
    token_id = tx.return_value
    assert rct_contract.ownerOf(token_id) == lender
    assert reputation_contract.isDelinquent(defaulter) == True
    assert rct_contract.debtCount(defaulter) == 1

    # 2. Lender transfers the token to the defaulter
    rct_contract.transferFrom(lender, defaulter, token_id, {'from': lender})
    assert rct_contract.ownerOf(token_id) == defaulter

    # 3. Defaulter (now the owner) burns the token
    burn_tx = rct_contract.burn(token_id, {'from': defaulter})

    # Assert: State is cleaned up
    assert rct_contract.debtCount(defaulter) == 0
    assert reputation_contract.isDelinquent(defaulter) == False
    
    # Assert: Token is gone
    with reverts("ERC721: invalid token ID"):
        rct_contract.ownerOf(token_id)

    # Assert: Event was emitted
    assert 'ClaimBurned' in burn_tx.events
    assert burn_tx.events['ClaimBurned']['tokenId'] == token_id
    assert burn_tx.events['ClaimBurned']['burner'] == defaulter


def test_burn_not_last_debt(contracts):
    """
    Tests that burning an RCT when others are outstanding correctly decrements
    the debt count but does not clear the delinquent status.
    """
    reputation_contract, rct_contract = contracts
    minter = accounts[1]
    defaulter = accounts[3]
    lender = accounts[4]

    # Arrange: Mint two RCTs against the defaulter
    tx1 = rct_contract.mint(401, defaulter, lender, 1000, accounts[5], {'from': minter})
    token_id_1 = tx1.return_value
    rct_contract.mint(402, defaulter, lender, 2000, accounts[6], {'from': minter})
    
    assert rct_contract.debtCount(defaulter) == 2
    assert reputation_contract.isDelinquent(defaulter) == True

    # Act: Lender burns the first token (assuming they still own it)
    rct_contract.burn(token_id_1, {'from': lender})

    # Assert: Debt count is now 1, but defaulter is still delinquent
    assert rct_contract.debtCount(defaulter) == 1
    assert reputation_contract.isDelinquent(defaulter) == True