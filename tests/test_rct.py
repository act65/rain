"""
ReputationClaimToken: the claim on a defaulted promise.

Claims tested:
  - an RCT exists only for a promise the CalculusEngine records as Defaulted, is
    minted only by that promise's script, only once, and copies its terms from the log;
  - a user is delinquent exactly while they have outstanding RCTs against them;
  - only the holder (or someone they approved) can burn an RCT.
"""
import pytest
from helpers import E18, accounts, action_id_of, advance, chain, deploy_reputation, ev, project, promise_id_of, reverts, token_id_of

DURATION = 100


@pytest.fixture
def contracts():
    """
    Returns (reputation_contract, rct_contract, engine).
    accounts[0] is the admin and accounts[1] plays the script. The protocol fee is zero.
    """
    admin = accounts[0]
    usdc = project.CurrencyToken.deploy(sender=admin)
    reputation_contract = deploy_reputation(admin)
    engine = project.CalculusEngine.deploy(usdc.address, accounts[9], 0, 0, E18, sender=admin)
    rct_contract = project.ReputationClaimToken.deploy(reputation_contract.address, engine.address, sender=admin)
    reputation_contract.setRctContract(rct_contract.address, sender=admin)
    return reputation_contract, rct_contract, engine


def make_promise(engine, promisor, promisee, amount=1000, script=None):
    script = script or accounts[1]
    engine.setScriptAuthorization(script, True, sender=promisor)
    action_id = action_id_of(engine.monitoredAction(promisor, sender=script))
    return promise_id_of(engine.monitoredPromise(
        action_id, promisor, promisee, engine.usdcToken(), amount, chain.pending_timestamp + DURATION, sender=script
    ))


def default_promise(engine, promisor, promisee, amount=1000, script=None):
    script = script or accounts[1]
    promise_id = make_promise(engine, promisor, promisee, amount, script)
    advance(DURATION + 1)
    engine.monitoredDefault(promise_id, sender=script)
    return promise_id


def test_deployment_and_setup(contracts):
    reputation_contract, rct_contract, engine = contracts
    assert rct_contract.name() == "Rain Reputation Claim"
    assert rct_contract.symbol() == "RCT"
    assert rct_contract.rainReputation() == reputation_contract.address
    assert rct_contract.calculusEngine() == engine.address


# --- Minting is bound to the engine's log ---

def test_cannot_mint_for_a_promise_that_is_not_defaulted(contracts):
    reputation_contract, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]

    with reverts("RCT: Promise is not defaulted"):
        rct_contract.mint(999, sender=script)  # no such promise

    pending = make_promise(engine, defaulter, lender)
    with reverts("RCT: Promise is not defaulted"):
        rct_contract.mint(pending, sender=script)

    kept = make_promise(engine, defaulter, lender)
    engine.monitoredFulfillment(kept, sender=script)
    with reverts("RCT: Promise is not defaulted"):
        rct_contract.mint(kept, sender=script)

    assert not reputation_contract.isDelinquent(defaulter)


def test_only_the_promises_script_can_mint(contracts):
    reputation_contract, rct_contract, engine = contracts
    defaulter, lender = accounts[3], accounts[4]
    promise_id = default_promise(engine, defaulter, lender)
    for caller in (accounts[0], lender, defaulter, accounts[7]):
        with reverts("RCT: Caller is not the script for this promise"):
            rct_contract.mint(promise_id, sender=caller)
    assert not reputation_contract.isDelinquent(defaulter)


def test_a_script_cannot_make_a_non_consenting_user_delinquent(contracts):
    """The whole path to delinquency starts with a promise, which needs the promisor's authorization."""
    _, _, engine = contracts
    rogue_script, victim = accounts[7], accounts[3]
    action_id = action_id_of(engine.monitoredAction(rogue_script, sender=rogue_script))
    with reverts("CalculusEngine: Script not authorized by promisor"):
        engine.monitoredPromise(action_id, victim, rogue_script, engine.usdcToken(), 1, chain.pending_timestamp + 1, sender=rogue_script)


def test_claim_can_be_minted_only_once_per_promise(contracts):
    _, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]
    promise_id = default_promise(engine, defaulter, lender)
    token_id = token_id_of(rct_contract.mint(promise_id, sender=script))
    assert rct_contract.claimForPromise(promise_id) == token_id

    with reverts("RCT: Claim already minted for this promise"):
        rct_contract.mint(promise_id, sender=script)

    rct_contract.burn(token_id, sender=lender)  # not even after the claim was settled
    with reverts("RCT: Claim already minted for this promise"):
        rct_contract.mint(promise_id, sender=script)
    assert rct_contract.debtCount(defaulter) == 0


def test_mint_first_offense_and_delinquency(contracts):
    """
    The first RCT against a user makes them delinquent; its terms come from the promise.
    """
    reputation_contract, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]
    shortfall = 5000
    promise_id = default_promise(engine, defaulter, lender, amount=shortfall)

    assert reputation_contract.isDelinquent(defaulter) == False

    tx = rct_contract.mint(promise_id, sender=script)
    token_id = token_id_of(tx)

    assert rct_contract.ownerOf(token_id) == lender
    assert rct_contract.debtCount(defaulter) == 1
    assert reputation_contract.isDelinquent(defaulter) == True
    assert reputation_contract.isDelinquent(lender) == False

    claim = rct_contract.claims(token_id)
    assert claim['promiseId'] == promise_id
    assert claim['defaulterAddress'] == defaulter
    assert claim['originalLenderAddress'] == lender
    assert claim['shortfallAmount'] == shortfall
    assert claim['loanContractAddress'] == script
    assert claim['defaultTimestamp'] == tx.timestamp

    event = ev(tx)['ClaimMinted']
    assert (event['tokenId'], event['defaulter'], event['originalLender'], event['shortfallAmount']) == (
        token_id, defaulter, lender, shortfall)


def test_mint_subsequent_offense(contracts):
    """
    A second offense increments the debt count; the user stays delinquent.
    """
    reputation_contract, rct_contract, engine = contracts
    script, defaulter = accounts[1], accounts[3]

    rct_contract.mint(default_promise(engine, defaulter, accounts[4]), sender=script)
    assert rct_contract.debtCount(defaulter) == 1

    rct_contract.mint(default_promise(engine, defaulter, accounts[5]), sender=script)
    assert rct_contract.debtCount(defaulter) == 2
    assert reputation_contract.isDelinquent(defaulter) == True


def test_mint_to_a_contract_that_cannot_receive_nfts_does_not_block_the_default(contracts):
    reputation_contract, rct_contract, engine = contracts
    script, defaulter = accounts[1], accounts[3]
    lender_contract = engine.usdcToken()  # a contract with no onERC721Received
    promise_id = default_promise(engine, defaulter, lender_contract)
    token_id = token_id_of(rct_contract.mint(promise_id, sender=script))
    assert rct_contract.ownerOf(token_id) == lender_contract
    assert reputation_contract.isDelinquent(defaulter)


# --- Burning ---

def test_burn_permissions_by_unapproved_non_owner(contracts):
    """
    Ensures an unapproved, non-owner account cannot burn the RCT.
    """
    _, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]
    token_id = token_id_of(rct_contract.mint(default_promise(engine, defaulter, lender), sender=script))

    for caller in (defaulter, script, accounts[0], accounts[9]):
        with reverts("ERC721: burn caller is not owner nor approved"):
            rct_contract.burn(token_id, sender=caller)
    assert rct_contract.ownerOf(token_id) == lender


def test_burn_by_approved_address(contracts):
    """
    A non-owner who has been approved can burn the token (the LoanScript workflow).
    """
    reputation_contract, rct_contract, engine = contracts
    script, defaulter, owner, approved_burner = accounts[1], accounts[5], accounts[3], accounts[4]
    token_id = token_id_of(rct_contract.mint(default_promise(engine, defaulter, owner), sender=script))

    rct_contract.approve(approved_burner, token_id, sender=owner)
    burn_tx = rct_contract.burn(token_id, sender=approved_burner)

    with reverts("ERC721: invalid token ID"):
        rct_contract.ownerOf(token_id)
    assert ev(burn_tx)['ClaimBurned']['burner'] == approved_burner
    assert not reputation_contract.isDelinquent(defaulter)


def test_full_lifecycle_reacquire_and_burn(contracts):
    """
    Mint -> lender transfers the RCT to the defaulter -> defaulter burns it -> no longer delinquent.
    """
    reputation_contract, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]
    token_id = token_id_of(rct_contract.mint(default_promise(engine, defaulter, lender), sender=script))

    rct_contract.transferFrom(lender, defaulter, token_id, sender=lender)
    assert rct_contract.ownerOf(token_id) == defaulter
    assert reputation_contract.isDelinquent(defaulter) == True  # holding your own RCT is not enough

    burn_tx = rct_contract.burn(token_id, sender=defaulter)

    assert rct_contract.debtCount(defaulter) == 0
    assert reputation_contract.isDelinquent(defaulter) == False
    with reverts("ERC721: invalid token ID"):
        rct_contract.ownerOf(token_id)
    assert rct_contract.claims(token_id)['defaulterAddress'] == "0x" + "00" * 20
    assert ev(burn_tx)['ClaimBurned']['tokenId'] == token_id
    assert ev(burn_tx)['ClaimBurned']['burner'] == defaulter


def test_burn_not_last_debt(contracts):
    """
    Burning one of several RCTs decrements the debt count but leaves the user delinquent.
    """
    reputation_contract, rct_contract, engine = contracts
    script, defaulter, lender = accounts[1], accounts[3], accounts[4]
    token_id_1 = token_id_of(rct_contract.mint(default_promise(engine, defaulter, lender), sender=script))
    token_id_2 = token_id_of(rct_contract.mint(default_promise(engine, defaulter, lender), sender=script))

    rct_contract.burn(token_id_1, sender=lender)
    assert rct_contract.debtCount(defaulter) == 1
    assert reputation_contract.isDelinquent(defaulter) == True

    rct_contract.burn(token_id_2, sender=lender)
    assert rct_contract.debtCount(defaulter) == 0
    assert reputation_contract.isDelinquent(defaulter) == False


def test_debts_of_different_users_are_independent(contracts):
    reputation_contract, rct_contract, engine = contracts
    script, a, b, lender = accounts[1], accounts[3], accounts[5], accounts[4]
    token_a = token_id_of(rct_contract.mint(default_promise(engine, a, lender), sender=script))
    rct_contract.mint(default_promise(engine, b, lender), sender=script)
    rct_contract.burn(token_a, sender=lender)
    assert not reputation_contract.isDelinquent(a)
    assert reputation_contract.isDelinquent(b)
