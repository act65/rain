"""
CalculusEngine: the log of promises and transfers.

Claims tested:
  - anyone can act as a script, but a script only has the powers each user gave it:
    authorization to make promises in their name, and per-asset allowances;
  - the protocol fee is charged per promise, to the promisor, and reaches the treasury;
  - a promise is resolved exactly once, by its own script, on the right side of its deadline.
"""
import pytest
from helpers import accounts, action_id_of, advance, chain, ev, project, promise_id_of, reverts, token_id_of

MAX_UINT = 2**256 - 1


@pytest.fixture
def ready(contracts):
    """Alice has given `script` what it needs to make fee-paying promises in her name."""
    engine, usdc = contracts["calculus_engine"], contracts["currency_token"]
    alice, script = contracts["user_alice"], contracts["script_contract_owner"]
    usdc.approve(engine.address, MAX_UINT, sender=alice)
    engine.setScriptAuthorization(script, True, sender=alice)
    engine.approveScript(script, usdc.address, 10 * contracts["initial_fee"], sender=alice)
    return contracts


def open_action(contracts, user=None, script=None):
    engine = contracts["calculus_engine"]
    return action_id_of(engine.monitoredAction(
        user or contracts["user_alice"], sender=script or contracts["script_contract_owner"]
    ))


def open_promise(contracts, action_id, amount=1000, duration=3600):
    engine = contracts["calculus_engine"]
    return promise_id_of(engine.monitoredPromise(
        action_id, contracts["user_alice"], contracts["user_bob"], contracts["currency_token"].address,
        amount, chain.pending_timestamp + duration, sender=contracts["script_contract_owner"],
    ))


def test_deployment_and_initial_state(contracts):
    engine = contracts["calculus_engine"]
    assert engine.usdcToken() == contracts["currency_token"].address
    assert engine.treasuryAddress() == contracts["treasury"].address
    assert (engine.feeBps(), engine.minFee(), engine.pointPrice()) == (0, contracts["initial_fee"], 10**18)
    assert engine.hasRole(engine.DEFAULT_ADMIN_ROLE(), contracts["deployer"])
    assert not engine.hasRole(engine.DEFAULT_ADMIN_ROLE(), contracts["script_contract_owner"])


# --- User permissions ---

def test_user_permissions_are_per_user_and_per_script(contracts):
    engine, usdc = contracts["calculus_engine"], contracts["currency_token"]
    alice, bob = contracts["user_alice"], contracts["user_bob"]
    script, other = contracts["script_contract_owner"], contracts["malicious_script_owner"]

    tx = engine.setScriptAuthorization(script, True, sender=alice)
    assert ev(tx)['ScriptAuthorizationSet']['authorized'] == True
    tx = engine.approveScript(script, usdc.address, 123, sender=alice)
    assert ev(tx)['ScriptApproval']['amount'] == 123
    tx = engine.setScriptNftApproval(script, contracts["rct_contract"].address, True, sender=alice)
    assert ev(tx)['ScriptNftApprovalSet']['approved'] == True

    assert engine.isScriptAuthorized(alice, script)
    assert engine.scriptAllowance(alice, script, usdc.address) == 123
    assert engine.scriptNftApproval(alice, script, contracts["rct_contract"].address)
    # Nothing leaks to another script or another user
    assert not engine.isScriptAuthorized(alice, other) and not engine.isScriptAuthorized(bob, script)
    assert engine.scriptAllowance(alice, other, usdc.address) == 0
    assert engine.scriptAllowance(bob, script, usdc.address) == 0

    engine.setScriptAuthorization(script, False, sender=alice)
    assert not engine.isScriptAuthorized(alice, script)


# --- monitoredAction ---

def test_action_is_free_and_recorded(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, script = ready["user_alice"], ready["script_contract_owner"]
    before = usdc.balanceOf(alice)

    tx = engine.monitoredAction(alice, sender=script)

    assert action_id_of(tx) == 1
    assert usdc.balanceOf(alice) == before and usdc.balanceOf(ready["treasury"]) == 0
    event = ev(tx)['ActionCreated']
    assert (event['actionId'], event['user'], event['script']) == (1, alice, script)
    assert engine.actions(1) == (alice, script)
    assert open_action(ready) == 2


def test_action_requires_the_users_authorization(contracts):
    engine, alice, script = contracts["calculus_engine"], contracts["user_alice"], contracts["script_contract_owner"]
    with reverts("CalculusEngine: Script not authorized by user"):
        engine.monitoredAction(alice, sender=script)


def test_anyone_can_act_as_a_script(contracts):
    """No role is needed: an arbitrary account opens an action for itself."""
    engine, outsider = contracts["calculus_engine"], contracts["malicious_script_owner"]
    action_id = action_id_of(engine.monitoredAction(outsider, sender=outsider))
    assert engine.actions(action_id) == (outsider, outsider)


# --- monitoredPromise ---

def test_promise_stores_all_fields(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    action_id = open_action(ready)
    deadline = chain.pending_timestamp + 500
    tx = engine.monitoredPromise(
        action_id, ready["user_alice"], ready["user_bob"], usdc.address, 42, deadline,
        sender=ready["script_contract_owner"],
    )
    promise_id = promise_id_of(tx)
    assert promise_id == 1
    p = engine.promises(promise_id)
    assert (p['actionId'], p['promisor'], p['promisee'], p['asset'], p['amount'], p['deadline'], p['status']) == (
        action_id, ready["user_alice"], ready["user_bob"], usdc.address, 42, deadline, 0)
    event = ev(tx)['PromiseCreated']
    assert (event['promiseId'], event['actionId'], event['promisor']) == (promise_id, action_id, ready["user_alice"])


def test_every_promise_pays_the_fee_to_the_treasury(ready):
    """The fee is per promise: attaching more promises to one action costs more."""
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, script, fee = ready["user_alice"], ready["script_contract_owner"], ready["initial_fee"]
    action_id = open_action(ready)
    alice_before = usdc.balanceOf(alice)

    for n in range(1, 4):
        assert open_promise(ready, action_id) == n
        assert usdc.balanceOf(ready["treasury"]) == n * fee
        assert usdc.balanceOf(alice) == alice_before - n * fee
        assert engine.scriptAllowance(alice, script, usdc.address) == (10 - n) * fee
    assert usdc.balanceOf(script) == 0 and usdc.balanceOf(engine) == 0


def test_promise_requires_the_promisors_authorization(ready):
    """A script cannot make a promise in the name of someone who never agreed to use it."""
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, bob, script = ready["user_alice"], ready["user_bob"], ready["script_contract_owner"]
    action_id = open_action(ready)
    with reverts("CalculusEngine: Script not authorized by promisor"):
        engine.monitoredPromise(action_id, bob, alice, usdc.address, 1, chain.pending_timestamp + 10, sender=script)

    engine.setScriptAuthorization(script, False, sender=alice)  # Alice changes her mind
    with reverts("CalculusEngine: Script not authorized by promisor"):
        open_promise(ready, action_id)


def test_promise_requires_fee_allowance_for_the_script(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, script, fee = ready["user_alice"], ready["script_contract_owner"], ready["initial_fee"]
    action_id = open_action(ready)
    engine.approveScript(script, usdc.address, fee - 1, sender=alice)
    with reverts("CalculusEngine: Insufficient script allowance"):
        open_promise(ready, action_id)

    engine.approveScript(script, usdc.address, fee, sender=alice)
    usdc.approve(engine.address, 0, sender=alice)  # the engine itself must also be approved on the token
    with reverts("ERC20: insufficient allowance"):
        open_promise(ready, action_id)
    assert usdc.balanceOf(ready["treasury"]) == 0


def test_promisor_must_be_able_to_afford_the_fee(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, bob, script = ready["user_alice"], ready["user_bob"], ready["script_contract_owner"]
    usdc.approve(engine.address, MAX_UINT, sender=bob)  # Bob holds no tokens
    engine.setScriptAuthorization(script, True, sender=bob)
    engine.approveScript(script, usdc.address, MAX_UINT, sender=bob)
    action_id = open_action(ready)
    with reverts("ERC20: transfer amount exceeds balance"):
        engine.monitoredPromise(action_id, bob, alice, usdc.address, 1, chain.pending_timestamp + 10, sender=script)


def test_cannot_promise_to_yourself(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, script = ready["user_alice"], ready["script_contract_owner"]
    action_id = open_action(ready)
    with reverts("CalculusEngine: Cannot promise to yourself"):
        engine.monitoredPromise(action_id, alice, alice, usdc.address, 1, chain.pending_timestamp + 10, sender=script)


def test_promise_must_belong_to_the_callers_action(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, bob = ready["user_alice"], ready["user_bob"]
    script, other = ready["script_contract_owner"], ready["malicious_script_owner"]
    action_id = open_action(ready)
    engine.setScriptAuthorization(other, True, sender=alice)  # even an authorized script...
    for bad_action in (action_id, action_id + 1, 0):  # ...cannot add to someone else's (or no) action
        with reverts("CalculusEngine: Caller is not the original script for this action"):
            engine.monitoredPromise(bad_action, alice, bob, usdc.address, 1, chain.pending_timestamp + 10, sender=other)


def test_zero_fee_promise_needs_no_allowance_but_still_needs_authorization(contracts):
    engine, usdc = contracts["calculus_engine"], contracts["currency_token"]
    alice, bob, script = contracts["user_alice"], contracts["user_bob"], contracts["script_contract_owner"]
    engine.setFeeParameters(0, 0, sender=contracts["deployer"])
    engine.setScriptAuthorization(script, True, sender=bob)
    action_id = action_id_of(engine.monitoredAction(bob, sender=script))

    assert promise_id_of(engine.monitoredPromise(action_id, bob, alice, usdc.address, 1, chain.pending_timestamp + 10, sender=script)) == 1
    with reverts("CalculusEngine: Script not authorized by promisor"):
        engine.monitoredPromise(action_id, alice, bob, usdc.address, 1, chain.pending_timestamp + 10, sender=script)
    assert usdc.balanceOf(contracts["treasury"]) == 0


# --- The fee: proportional to the amount promised, with a minimum; recorded with the promise ---

def test_fee_parameters_are_admin_only(ready):
    engine = ready["calculus_engine"]
    with reverts("Admin only"):
        engine.setFeeParameters(1, 1, sender=ready["script_contract_owner"])
    with reverts("Admin only"):
        engine.setPointPrice(1, sender=ready["script_contract_owner"])
    with reverts("CalculusEngine: Point price must be positive"):
        engine.setPointPrice(0, sender=ready["deployer"])

    tx = engine.setFeeParameters(50, 7, sender=ready["deployer"])
    assert (engine.feeBps(), engine.minFee()) == (50, 7)
    assert (ev(tx)['FeeParametersUpdated']['feeBps'], ev(tx)['FeeParametersUpdated']['minFee']) == (50, 7)
    tx = engine.setPointPrice(123, sender=ready["deployer"])
    assert engine.pointPrice() == 123 and ev(tx)['PointPriceUpdated']['pointPrice'] == 123


def test_flat_fee_is_recorded_with_the_promise(ready):
    engine = ready["calculus_engine"]
    promise_id = open_promise(ready, open_action(ready))
    assert engine.promises(promise_id)['feePaid'] == ready["initial_fee"]


@pytest.mark.parametrize("amount,expected_fee", [
    (0, 5),            # the minimum
    (400, 5),          # 1% of 400 is 4: still the minimum
    (500, 5),
    (1_000, 10),       # 1%
    (123_456, 1_234),  # rounded down
])
def test_fee_is_proportional_to_the_amount_promised_with_a_minimum(ready, amount, expected_fee):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    engine.setFeeParameters(100, 5, sender=ready["deployer"])  # 1%, at least 5
    assert engine.quoteFee(usdc.address, amount) == expected_fee

    alice_before = usdc.balanceOf(ready["user_alice"])
    promise_id = open_promise(ready, open_action(ready), amount=amount)

    assert engine.promises(promise_id)['feePaid'] == expected_fee
    assert usdc.balanceOf(ready["treasury"]) == expected_fee
    assert usdc.balanceOf(ready["user_alice"]) == alice_before - expected_fee


def test_promise_of_another_asset_pays_the_minimum_fee(ready):
    """Only promises in the protocol currency have a size the fee can be a fraction of."""
    engine, rct = ready["calculus_engine"], ready["rct_contract"]
    engine.setFeeParameters(100, 5, sender=ready["deployer"])
    assert engine.quoteFee(rct.address, 10**30) == 5
    tx = engine.monitoredPromise(
        open_action(ready), ready["user_alice"], ready["user_bob"], rct.address, 10**30, chain.pending_timestamp + 100,
        sender=ready["script_contract_owner"],
    )
    assert engine.promises(promise_id_of(tx))['feePaid'] == 5


def test_changing_the_fee_does_not_change_what_earlier_promises_paid(ready):
    engine = ready["calculus_engine"]
    action_id = open_action(ready)
    first = open_promise(ready, action_id)
    engine.setFeeParameters(0, 7, sender=ready["deployer"])
    second = open_promise(ready, action_id)
    assert engine.promises(first)['feePaid'] == ready["initial_fee"]
    assert engine.promises(second)['feePaid'] == 7


# --- resolution ---

def test_fulfillment(ready):
    engine, script = ready["calculus_engine"], ready["script_contract_owner"]
    promise_id = open_promise(ready, open_action(ready))
    tx = engine.monitoredFulfillment(promise_id, sender=script)
    assert engine.promises(promise_id)['status'] == 1  # Fulfilled
    assert ev(tx)['PromiseFulfilled']['promiseId'] == promise_id


def test_default_only_after_deadline_and_fulfillment_only_before(ready):
    engine, script = ready["calculus_engine"], ready["script_contract_owner"]
    promise_id = open_promise(ready, open_action(ready), duration=100)

    with reverts("CalculusEngine: Promise deadline has not passed"):
        engine.monitoredDefault(promise_id, sender=script)

    advance(101)

    with reverts("CalculusEngine: Promise deadline has passed"):
        engine.monitoredFulfillment(promise_id, sender=script)

    tx = engine.monitoredDefault(promise_id, sender=script)
    assert engine.promises(promise_id)['status'] == 2  # Defaulted
    assert ev(tx)['PromiseDefaulted']['promiseId'] == promise_id


def test_resolved_promise_cannot_be_resolved_again(ready):
    engine, script = ready["calculus_engine"], ready["script_contract_owner"]
    action_id = open_action(ready)
    kept = open_promise(ready, action_id, duration=100)
    broken = open_promise(ready, action_id, duration=100)

    engine.monitoredFulfillment(kept, sender=script)
    with reverts("CalculusEngine: Promise not pending"):
        engine.monitoredFulfillment(kept, sender=script)

    advance(101)
    with reverts("CalculusEngine: Promise not pending"):
        engine.monitoredDefault(kept, sender=script)

    engine.monitoredDefault(broken, sender=script)
    with reverts("CalculusEngine: Promise not pending"):
        engine.monitoredDefault(broken, sender=script)
    assert engine.promises(kept)['status'] == 1 and engine.promises(broken)['status'] == 2


@pytest.mark.parametrize("fn", ["monitoredFulfillment", "monitoredDefault"])
def test_only_the_promises_script_can_resolve_it(ready, fn):
    engine = ready["calculus_engine"]
    promise_id = open_promise(ready, open_action(ready))
    for caller in (ready["user_alice"], ready["user_bob"], ready["malicious_script_owner"], ready["deployer"]):
        with reverts("CalculusEngine: Caller is not the original script for this action"):
            getattr(engine, fn)(promise_id, sender=caller)
    with reverts("CalculusEngine: Caller is not the original script for this action"):
        getattr(engine, fn)(999, sender=ready["script_contract_owner"])  # unknown promise
    assert engine.promises(promise_id)['status'] == 0


def test_fulfillment_is_an_assertion_by_the_script(ready):
    """
    Characterisation: the engine records what the script says. It does not check
    that the promised asset actually moved. (Trusting a script is the user's choice,
    made when they authorize it.)
    """
    engine, usdc, bob = ready["calculus_engine"], ready["currency_token"], ready["user_bob"]
    promise_id = open_promise(ready, open_action(ready), amount=10**24)
    engine.monitoredFulfillment(promise_id, sender=ready["script_contract_owner"])
    assert engine.promises(promise_id)['status'] == 1
    assert usdc.balanceOf(bob) == 0


# --- transfers ---

def test_monitored_transfer(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, bob, script = ready["user_alice"], ready["user_bob"], ready["script_contract_owner"]
    action_id = open_action(ready)
    engine.approveScript(script, usdc.address, 800, sender=alice)
    before = usdc.balanceOf(alice)

    tx = engine.monitoredTransfer(action_id, usdc.address, alice, bob, 500, sender=script)

    assert usdc.balanceOf(bob) == 500 and usdc.balanceOf(alice) == before - 500
    assert engine.scriptAllowance(alice, script, usdc.address) == 300
    event = ev(tx)['ValueTransferred']
    assert (event['actionId'], event['asset'], event['from'], event['to'], event['amount']) == (
        action_id, usdc.address, alice, bob, 500)

    with reverts("CalculusEngine: Insufficient script allowance"):
        engine.monitoredTransfer(action_id, usdc.address, alice, bob, 301, sender=script)


def test_unlimited_script_allowance_is_not_consumed(ready):
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, bob, script = ready["user_alice"], ready["user_bob"], ready["script_contract_owner"]
    engine.approveScript(script, usdc.address, MAX_UINT, sender=alice)
    engine.monitoredTransfer(open_action(ready), usdc.address, alice, bob, 500, sender=script)
    assert engine.scriptAllowance(alice, script, usdc.address) == MAX_UINT


def test_allowance_is_scoped_to_the_script_it_was_given_to(ready):
    """
    Alice's allowance to one script (and her token approval of the engine) gives
    another script nothing, even inside an action that script legitimately opened.
    """
    engine, usdc = ready["calculus_engine"], ready["currency_token"]
    alice, attacker = ready["user_alice"], ready["malicious_script_owner"]
    engine.approveScript(ready["script_contract_owner"], usdc.address, 10**21, sender=alice)

    own_action = action_id_of(engine.monitoredAction(attacker, sender=attacker))
    with reverts("CalculusEngine: Insufficient script allowance"):
        engine.monitoredTransfer(own_action, usdc.address, alice, attacker, 1, sender=attacker)

    victims_action = open_action(ready)  # and it cannot piggy-back on the trusted script's action
    with reverts("CalculusEngine: Caller is not the original script for this action"):
        engine.monitoredTransfer(victims_action, usdc.address, alice, attacker, 1, sender=attacker)
    assert usdc.balanceOf(attacker) == 0


def test_script_can_move_its_own_funds_without_an_allowance(contracts):
    engine, usdc = contracts["calculus_engine"], contracts["currency_token"]
    alice, script = contracts["user_alice"], contracts["script_contract_owner"]
    usdc.transfer(script, 100, sender=alice)
    usdc.approve(engine.address, 100, sender=script)
    action_id = action_id_of(engine.monitoredAction(script, sender=script))
    engine.monitoredTransfer(action_id, usdc.address, script, alice, 100, sender=script)
    assert usdc.balanceOf(script) == 0


def test_monitored_nft_transfer(ready):
    engine, rct = ready["calculus_engine"], ready["rct_contract"]
    alice, bob, script = ready["user_alice"], ready["user_bob"], ready["script_contract_owner"]
    other = ready["malicious_script_owner"]

    # Alice breaks a promise to Bob, so Bob holds a claim (an NFT) on her
    action_id = open_action(ready)
    promise_id = open_promise(ready, action_id, duration=10)
    advance(11)
    engine.monitoredDefault(promise_id, sender=script)
    token_id = token_id_of(rct.mint(promise_id, sender=script))
    assert rct.ownerOf(token_id) == bob

    rct.setApprovalForAll(engine.address, True, sender=bob)  # ERC721 approval of the engine...
    with reverts("CalculusEngine: Script not approved for this collection"):  # ...is not enough
        engine.monitoredNftTransfer(action_id, rct.address, bob, alice, token_id, sender=script)

    engine.setScriptNftApproval(script, rct.address, True, sender=bob)
    with reverts("CalculusEngine: Caller is not the original script for this action"):
        engine.monitoredNftTransfer(action_id, rct.address, bob, other, token_id, sender=other)

    tx = engine.monitoredNftTransfer(action_id, rct.address, bob, alice, token_id, sender=script)
    assert rct.ownerOf(token_id) == alice
    event = ev(tx)['ValueTransferred']
    assert (event['asset'], event['from'], event['to'], event['amount']) == (rct.address, bob, alice, 1)
