import pytest
from brownie import reverts, chain

def test_deployment_and_initial_state(contracts):
    """
    Tests that the CalculusEngine is deployed with the correct initial state.
    """
    engine = contracts["calculus_engine"]
    
    # Check configuration
    assert engine.usdcToken() == contracts["currency_token"].address
    assert engine.treasuryAddress() == contracts["treasury"].address
    assert engine.protocolFee() == contracts["initial_fee"]

    # Check roles
    admin_role = engine.DEFAULT_ADMIN_ROLE()
    creator_role = engine.SESSION_CREATOR_ROLE()
    
    assert engine.hasRole(admin_role, contracts["deployer"])
    assert engine.hasRole(creator_role, contracts["script_contract_owner"])
    assert not engine.hasRole(creator_role, contracts["user_alice"])

def test_monitored_action_success(contracts):
    """
    Tests a successful call to monitoredAction, checking fee transfer and event emission.
    """
    engine = contracts["calculus_engine"]
    usdc = contracts["currency_token"]
    alice = contracts["user_alice"]
    treasury = contracts["treasury"]
    script = contracts["script_contract_owner"]
    fee = contracts["initial_fee"]

    # Alice must first approve the engine to spend her USDC for the fee
    usdc.approve(engine.address, fee, {'from': alice})

    # Act: The script contract initiates an action on behalf of Alice
    tx = engine.monitoredAction(alice, {'from': script})
    action_id = tx.return_value

    # Assert
    assert action_id == 1
    assert usdc.balanceOf(treasury) == fee
    assert 'ActionCreated' in tx.events
    assert tx.events['ActionCreated']['actionId'] == 1
    assert tx.events['ActionCreated']['user'] == alice
    assert tx.events['ActionCreated']['script'] == script

def test_monitored_action_permissions(contracts):
    """
    Ensures only accounts with SESSION_CREATOR_ROLE can call monitoredAction.
    """
    engine = contracts["calculus_engine"]
    alice = contracts["user_alice"]

    # Attempt to call from Alice's account, which lacks the role
    with reverts("CalculusEngine: Caller is not a session creator"):
        engine.monitoredAction(alice, {'from': alice})

def test_monitored_promise_and_fulfillment(contracts):
    """
    Tests the full lifecycle of a promise: creation and fulfillment.
    """
    engine = contracts["calculus_engine"]
    usdc = contracts["currency_token"]
    alice = contracts["user_alice"]
    bob = contracts["user_bob"]
    script = contracts["script_contract_owner"]
    fee = contracts["initial_fee"]

    # --- Setup: Create an action ---
    usdc.approve(engine.address, fee, {'from': alice})
    action_tx = engine.monitoredAction(alice, {'from': script})
    action_id = action_tx.return_value

    # --- Act 1: Create a promise ---
    deadline = chain.time() + 3600 # 1 hour from now
    promise_tx = engine.monitoredPromise(
        action_id,
        alice, # promisor
        bob,   # promisee
        usdc.address,
        1000,
        deadline,
        {'from': script}
    )
    promise_id = promise_tx.return_value

    # --- Assert 1: Check promise state ---
    assert promise_id == 1
    promise_data = engine.promises(promise_id)
    assert promise_data['promisor'] == alice
    assert promise_data['status'] == 0 # Enum Pending
    assert 'PromiseCreated' in promise_tx.events
    assert promise_tx.events['PromiseCreated']['promiseId'] == promise_id

    # --- Act 2: Fulfill the promise ---
    fulfillment_tx = engine.monitoredFulfillment(promise_id, {'from': script})

    # --- Assert 2: Check fulfillment state ---
    assert engine.promises(promise_id)['status'] == 1 # Enum Fulfilled
    assert 'PromiseFulfilled' in fulfillment_tx.events
    assert fulfillment_tx.events['PromiseFulfilled']['promiseId'] == promise_id

def test_monitored_default(contracts):
    """
    Tests that a promise can be correctly marked as defaulted after its deadline.
    """
    engine = contracts["calculus_engine"]
    usdc = contracts["currency_token"]
    alice = contracts["user_alice"]
    bob = contracts["user_bob"]
    script = contracts["script_contract_owner"]
    fee = contracts["initial_fee"]

    # --- Setup: Create an action and a promise ---
    usdc.approve(engine.address, fee, {'from': alice})
    action_id = engine.monitoredAction(alice, {'from': script}).return_value
    deadline = chain.time() + 100 # Short deadline
    promise_id = engine.monitoredPromise(action_id, alice, bob, usdc.address, 500, deadline, {'from': script}).return_value

    # --- Act 1: Try to default before deadline (should fail) ---
    with reverts("CalculusEngine: Promise deadline has not passed"):
        engine.monitoredDefault(promise_id, {'from': script})

    # --- Act 2: Advance time past the deadline ---
    chain.sleep(101)
    chain.mine()

    # --- Act 3: Try to fulfill after deadline (should fail) ---
    with reverts("CalculusEngine: Promise deadline has passed"):
        engine.monitoredFulfillment(promise_id, {'from': script})

    # --- Act 4: Default the promise (should succeed) ---
    default_tx = engine.monitoredDefault(promise_id, {'from': script})

    # --- Assert ---
    assert engine.promises(promise_id)['status'] == 2 # Enum Defaulted
    assert 'PromiseDefaulted' in default_tx.events
    assert default_tx.events['PromiseDefaulted']['promiseId'] == promise_id

def test_wrong_script_reverts(contracts):
    """
    Ensures that a monitored function reverts if called by a script other
    than the one that initiated the action.
    """
    engine = contracts["calculus_engine"]
    usdc = contracts["currency_token"]
    alice = contracts["user_alice"]
    bob = contracts["user_bob"]
    legit_script = contracts["script_contract_owner"]
    fee = contracts["initial_fee"]
    
    # --- FIX: Define the attacker and grant it the required role ---
    attacker_script = contracts["malicious_script_owner"]
    creator_role = engine.SESSION_CREATOR_ROLE()
    engine.grantRole(creator_role, attacker_script, {'from': contracts["deployer"]})
    # Now the attacker_script passes the first 'require', but not the second.
    # ---

    # Setup: Create an action with the legitimate script
    usdc.approve(engine.address, fee, {'from': alice})
    action_id = engine.monitoredAction(alice, {'from': legit_script}).return_value

    # Act & Assert: Attacker script tries to create a promise using the actionId
    # This should now fail on the SECOND require statement, as intended.
    with reverts("CalculusEngine: Caller is not the original script for this action"):
        engine.monitoredPromise(
            action_id,
            alice,
            bob,
            usdc.address,
            100,
            chain.time() + 1000,
            {'from': attacker_script} # Use the new attacker
        )