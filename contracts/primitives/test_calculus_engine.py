import pytest
from brownie import CalculusEngine, accounts, interface, reverts # type: ignore

# --- Constants ---
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DEFAULT_PROTOCOL_FEE = 100 * 10**6 # Assuming 6 decimals for USDC

@pytest.fixture(scope="module")
def admin():
    return accounts[0]

@pytest.fixture(scope="module")
def session_creator():
    return accounts[1]

@pytest.fixture(scope="module")
def user_one():
    return accounts[2]

@pytest.fixture(scope="module")
def user_two():
    return accounts[3]

@pytest.fixture(scope="module")
def script_contract():
    # In a real test, this might be a deployed mock script contract
    return accounts[4]

@pytest.fixture(scope="module")
def usdc_token(admin, user_one):
    # Mock ERC20 token for USDC
    # For simplicity, we'll just use an account as a mock token address
    # and simulate transfers by checking balances (not implemented here for brevity)
    # In a full test suite, you'd deploy a mock ERC20 contract.
    token = admin.deploy(MockERC20, "Mock USDC", "mUSDC", 18) # Or use an existing mock
    token.mint(user_one, 1000 * 10**6, {"from": admin})
    token.mint(session_creator, 1000 * 10**6, {"from": admin})
    return token

@pytest.fixture(scope="module")
def mock_nft(admin, user_one):
    # Mock ERC721 token
    nft = admin.deploy(MockERC721, "Mock NFT", "mNFT")
    nft.mint(user_one, 1, {"from": admin})
    return nft

@pytest.fixture(scope="module")
def treasury(admin):
    # For the purpose of CalculusEngine tests, treasury is just an address
    return accounts[5]

@pytest.fixture(scope="module")
def calculus_engine(admin, usdc_token, treasury, session_creator):
    engine = admin.deploy(CalculusEngine, usdc_token.address, treasury.address, DEFAULT_PROTOCOL_FEE)
    engine.grantRole(engine.SESSION_CREATOR_ROLE(), session_creator, {"from": admin})
    return engine

# --- Mock Contracts (simplified for brevity) ---
# You would typically put these in a separate conftest.py or a mocks directory

@pytest.fixture(scope="session")
def MockERC20(project, accounts):
    # Assuming you have a simple ERC20 mock contract (e.g., from OpenZeppelin test helpers or your own)
    # This is a placeholder for where you'd load/deploy it.
    # For this example, let's assume it's available in Brownie's project artifacts
    # If not, you'd need to define/deploy it.
    # Let's define a very simple one here for completeness if not found.
    class MockERC20Contract:
        def __init__(self, name, symbol, decimals, deployer):
            self.name = name
            self.symbol = symbol
            self.decimals = decimals
            self.balances = {}
            self.allowances = {}
            self.address = deployer.address # Simplification
            self.deployer = deployer

        def mint(self, to, amount, tx_args=None):
            self.balances[to] = self.balances.get(to, 0) + amount
            return True

        def transfer(self, to, amount, tx_args=None):
            sender = tx_args['from']
            if self.balances.get(sender, 0) < amount:
                reverts("ERC20: transfer amount exceeds balance")
            self.balances[sender] -= amount
            self.balances[to] = self.balances.get(to, 0) + amount
            return True

        def transferFrom(self, sender, recipient, amount, tx_args=None):
            caller = tx_args['from']
            if self.allowances.get((sender, caller), 0) < amount:
                reverts("ERC20: insufficient allowance")
            if self.balances.get(sender, 0) < amount:
                reverts("ERC20: transfer amount exceeds balance")

            self.balances[sender] -= amount
            self.balances[recipient] = self.balances.get(recipient, 0) + amount
            self.allowances[(sender, caller)] -= amount
            return True

        def approve(self, spender, amount, tx_args=None):
            sender = tx_args['from']
            self.allowances[(sender, spender)] = amount
            return True

        def balanceOf(self, account):
            return self.balances.get(account, 0)

    # This is a very basic mock. In Brownie, you'd deploy a compiled contract.
    # For now, let's assume a contract `MockERC20` exists or use this simplified class.
    # Due to environment constraints, deploying actual contracts might be tricky here.
    # We'll proceed as if Brownie handles this. If `project.MockERC20` is not found,
    # these tests might need adjustment for the actual mock deployment.
    try:
        return project.MockERC20 # If you have a MockERC20.sol compiled
    except AttributeError:
        # Fallback to a conceptual mock if not available (won't actually deploy)
        # This part is tricky as the test needs a real contract instance.
        # For now, we'll assume the test setup can deploy a suitable mock.
        # The following line is a placeholder.
        print("Warning: MockERC20 contract not found in project, tests might not run as expected.")
        # A proper setup would deploy a MockERC20.sol
        # For this environment, we'll use a simplified approach if Brownie can't find it.
        # This is a placeholder for a deployable mock
        class DeployedMockERC20:
            def __init__(self, address):
                self.address = address
                # Mock methods would be called via Brownie's contract interaction
            def mint(self, to, amount, tx_params): pass
            def approve(self, spender, amount, tx_params): pass
            def transferFrom(self, sender, recipient, amount, tx_params): pass
            def balanceOf(self, account): return 0 # Placeholder

        # This fixture would ideally deploy a MockERC20.sol
        # token = accounts[0].deploy(project.MockERC20, "Mock USDC", "mUSDC", 6)
        # For now, let's create a dummy object that has an address attribute
        dummy_token_contract = type("DummyToken", (object,), {"address": accounts[9].address, "mint": lambda *args, **kwargs: True, "approve": lambda *args, **kwargs: True, "transferFrom": lambda *args, **kwargs: True, "balanceOf": lambda *args, **kwargs: 10**18 })
        return dummy_token_contract


@pytest.fixture(scope="session")
def MockERC721(project, accounts):
    # Similar to MockERC20, this assumes a MockERC721 contract is available.
    try:
        return project.MockERC721
    except AttributeError:
        print("Warning: MockERC721 contract not found in project, tests might not run as expected.")
        class DeployedMockERC721:
            def __init__(self, address):
                self.address = address
            def mint(self, to, token_id, tx_params): pass
            def ownerOf(self, token_id): return ZERO_ADDRESS # Placeholder
            def transferFrom(self, sender, recipient, token_id, tx_params): pass
            def approve(self, spender, token_id, tx_params): pass

        dummy_nft_contract = type("DummyNFT", (object,), {"address": accounts[8].address, "mint": lambda *args, **kwargs: True, "ownerOf": lambda *args, **kwargs: ZERO_ADDRESS, "transferFrom": lambda *args, **kwargs: True, "approve": lambda *args, **kwargs: True})
        return dummy_nft_contract


# --- Test Cases ---

def test_initial_state(calculus_engine, usdc_token, treasury, admin):
    assert calculus_engine.usdcToken() == usdc_token.address
    assert calculus_engine.treasuryAddress() == treasury.address
    assert calculus_engine.protocolFee() == DEFAULT_PROTOCOL_FEE
    assert calculus_engine.hasRole(calculus_engine.DEFAULT_ADMIN_ROLE(), admin)

def test_set_protocol_fee(calculus_engine, admin):
    new_fee = 200 * 10**6
    tx = calculus_engine.setProtocolFee(new_fee, {"from": admin})
    assert calculus_engine.protocolFee() == new_fee
    assert "FeeUpdated" in tx.events
    assert tx.events["FeeUpdated"]["newFee"] == new_fee

def test_set_protocol_fee_not_admin(calculus_engine, user_one):
    with reverts("Admin only"):
        calculus_engine.setProtocolFee(300 * 10**6, {"from": user_one})

def test_monitored_action(calculus_engine, usdc_token, user_one, session_creator, treasury):
    # Simulate user_one approving the session_creator (acting as script) to spend fee for them
    # This approval would typically happen on the usdc_token contract directly by user_one
    # For the mock, we assume approval is given to calculus_engine for simplicity,
    # though the actual transferFrom is from user_one to treasury.
    # A real test would involve: usdc_token.approve(calculus_engine.address, fee, {"from": user_one})

    # For this test, we assume session_creator has funds or approval to pay.
    # The `monitoredAction` is called by `session_creator`, fee is paid by `user_one`.
    # So, user_one must approve calculus_engine to pull fees.
    # However, the design is `usdcToken.transferFrom(user, treasuryAddress, protocolFee)`
    # This means `user` must approve `calculus_engine` to transfer `protocolFee` to `treasuryAddress`.

    # Because Brownie's default accounts don't have ERC20 methods,
    # and deploying a full mock within this environment is complex,
    # we'll focus on the logic within CalculusEngine, assuming token interactions work.
    # We will mock the transferFrom by ensuring the event is emitted.

    # Grant session_creator role to script_contract for this specific test path
    # (CalculusEngine expects msg.sender of monitoredAction to be the script)

    # To test fee transfer, user_one needs to approve the CalculusEngine contract
    # Let's assume this approval has been made on the usdc_token.
    # usdc_token.approve(calculus_engine.address, DEFAULT_PROTOCOL_FEE, {"from": user_one})

    # The `monitoredAction` is called by a `session_creator` (e.g., a script).
    # The fee is paid by `user`.
    # So, `user` (user_one) must have approved `calculus_engine` to spend `protocolFee` on their behalf.

    # This part is tricky without a fully functional ERC20 mock environment.
    # We will assume the transferFrom call would succeed if balances and allowances were correct.
    # The key is that `CalculusEngine` attempts the transfer.

    # To make this testable, let's assume `session_creator` is also the `user` for fee payment.
    # And `session_creator` has approved `calculus_engine`.
    # usdc_token.approve(calculus_engine.address, DEFAULT_PROTOCOL_FEE, {"from": session_creator})

    # Simulating approval (conceptual)
    # usdc_token.approve(calculus_engine.address, DEFAULT_PROTOCOL_FEE, {"from": user_one})

    tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})

    assert "ActionCreated" in tx.events
    action_id = tx.events["ActionCreated"]["actionId"]
    assert action_id == 1
    assert tx.events["ActionCreated"]["user"] == user_one
    assert tx.events["ActionCreated"]["script"] == session_creator

    action_data = calculus_engine.actions(action_id)
    assert action_data["user"] == user_one
    assert action_data["script"] == session_creator

    # Verifying fee transfer is hard without a live ERC20 that tracks balances.
    # We trust that `usdcToken.transferFrom` was called.
    # A more robust test would check balances of user_one and treasury.

def test_monitored_action_no_role(calculus_engine, user_one):
    with reverts("CalculusEngine: Caller is not a session creator"):
        calculus_engine.monitoredAction(user_one, {"from": user_one}) # user_one is not a session creator

def test_monitored_promise(calculus_engine, session_creator, user_one, user_two, usdc_token):
    # First, create an action
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]

    promisor = user_one
    promisee = user_two
    asset = usdc_token.address
    amount = 500 * 10**6
    deadline = 1700000000 # Some future timestamp

    promise_tx = calculus_engine.monitoredPromise(
        action_id, promisor, promisee, asset, amount, deadline,
        {"from": session_creator}
    )

    assert "PromiseCreated" in promise_tx.events
    promise_id = promise_tx.events["PromiseCreated"]["promiseId"]
    assert promise_id == 1
    assert promise_tx.events["PromiseCreated"]["actionId"] == action_id
    assert promise_tx.events["PromiseCreated"]["promisor"] == promisor

    p = calculus_engine.promises(promise_id)
    assert p["actionId"] == action_id
    assert p["promisor"] == promisor
    assert p["promisee"] == promisee
    assert p["asset"] == asset
    assert p["amount"] == amount
    assert p["deadline"] == deadline
    assert p["status"] == 0 # Pending

def test_monitored_promise_wrong_script(calculus_engine, session_creator, user_one, user_two, usdc_token, admin):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]

    # Grant admin session_creator role temporarily for this test case,
    # but admin was not the original script for action_id
    calculus_engine.grantRole(calculus_engine.SESSION_CREATOR_ROLE(), admin, {"from": accounts[0]})


    with reverts("CalculusEngine: Caller is not the original script for this action"):
        calculus_engine.monitoredPromise(
            action_id, user_one, user_two, usdc_token.address, 100, 1700000000,
            {"from": admin} # admin is a session creator, but not for this actionId
        )

def test_monitored_transfer(calculus_engine, session_creator, user_one, user_two, usdc_token):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]

    # Assume user_one has tokens and has approved calculus_engine to transfer them
    # usdc_token.approve(calculus_engine.address, 100 * 10**6, {"from": user_one})

    transfer_amount = 100 * 10**6
    tx = calculus_engine.monitoredTransfer(
        action_id, usdc_token.address, user_one, user_two, transfer_amount,
        {"from": session_creator}
    )

    assert "ValueTransferred" in tx.events
    evt = tx.events["ValueTransferred"]
    assert evt["actionId"] == action_id
    assert evt["asset"] == usdc_token.address
    assert evt["from"] == user_one
    assert evt["to"] == user_two
    assert evt["amount"] == transfer_amount
    # Actual balance changes would be verified with a full ERC20 mock.

def test_monitored_nft_transfer(calculus_engine, session_creator, user_one, user_two, mock_nft):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]

    token_id = 1 # Assuming user_one owns NFT with tokenId 1
    # mock_nft.approve(calculus_engine.address, token_id, {"from": user_one})

    tx = calculus_engine.monitoredNftTransfer(
        action_id, mock_nft.address, user_one, user_two, token_id,
        {"from": session_creator}
    )

    assert "ValueTransferred" in tx.events
    evt = tx.events["ValueTransferred"]
    assert evt["actionId"] == action_id
    assert evt["asset"] == mock_nft.address
    assert evt["from"] == user_one
    assert evt["to"] == user_two
    assert evt["amount"] == 1 # For NFTs, amount is 1
    # Actual ownership change would be verified with a full ERC721 mock.


def test_monitored_fulfillment(calculus_engine, session_creator, user_one, user_two, usdc_token, chain):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]
    deadline = chain.time() + 1000 # Future deadline
    promise_tx = calculus_engine.monitoredPromise(
        action_id, user_one, user_two, usdc_token.address, 100, deadline,
        {"from": session_creator}
    )
    promise_id = promise_tx.events["PromiseCreated"]["promiseId"]

    fulfill_tx = calculus_engine.monitoredFulfillment(promise_id, {"from": session_creator})
    assert "PromiseFulfilled" in fulfill_tx.events
    assert fulfill_tx.events["PromiseFulfilled"]["promiseId"] == promise_id
    assert calculus_engine.promises(promise_id)["status"] == 1 # Fulfilled

def test_monitored_fulfillment_after_deadline(calculus_engine, session_creator, user_one, user_two, usdc_token, chain):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]
    deadline = chain.time() + 100
    promise_tx = calculus_engine.monitoredPromise(
        action_id, user_one, user_two, usdc_token.address, 100, deadline,
        {"from": session_creator}
    )
    promise_id = promise_tx.events["PromiseCreated"]["promiseId"]

    chain.sleep(150) # Pass deadline
    chain.mine()

    with reverts("CalculusEngine: Promise deadline has passed"):
        calculus_engine.monitoredFulfillment(promise_id, {"from": session_creator})

def test_monitored_default_before_deadline(calculus_engine, session_creator, user_one, user_two, usdc_token, chain):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]
    deadline = chain.time() + 1000
    promise_tx = calculus_engine.monitoredPromise(
        action_id, user_one, user_two, usdc_token.address, 100, deadline,
        {"from": session_creator}
    )
    promise_id = promise_tx.events["PromiseCreated"]["promiseId"]

    with reverts("CalculusEngine: Promise deadline has not passed"):
        calculus_engine.monitoredDefault(promise_id, {"from": session_creator})


def test_monitored_default_after_deadline(calculus_engine, session_creator, user_one, user_two, usdc_token, chain):
    action_tx = calculus_engine.monitoredAction(user_one, {"from": session_creator})
    action_id = action_tx.events["ActionCreated"]["actionId"]
    deadline = chain.time() + 100
    promise_tx = calculus_engine.monitoredPromise(
        action_id, user_one, user_two, usdc_token.address, 100, deadline,
        {"from": session_creator}
    )
    promise_id = promise_tx.events["PromiseCreated"]["promiseId"]

    chain.sleep(150)
    chain.mine()

    default_tx = calculus_engine.monitoredDefault(promise_id, {"from": session_creator})
    assert "PromiseDefaulted" in default_tx.events
    assert default_tx.events["PromiseDefaulted"]["promiseId"] == promise_id
    assert calculus_engine.promises(promise_id)["status"] == 2 # Defaulted

# Note: ReentrancyGuard tests are typically more complex and involve setting up
# a malicious contract to call back into the CalculusEngine.
# For this scope, we assume OpenZeppelin's ReentrancyGuard works as intended.
# Testing actual token transfers requires a robust local blockchain environment
# with deployed mock ERC20/ERC721 contracts, which is beyond simple text file generation.
# The mock fixtures (MockERC20, MockERC721) are crucial and need to be correctly
# implemented and deployed in the Brownie test environment.
# The provided mock fixtures are conceptual placeholders if real mocks aren't found.
# The tests assume `brownie test` environment where `accounts`, `chain`, `project` are available.
# The `interface.IERC20` and `interface.IERC721` would also be used by Brownie
# to interact with token contracts if they were fully mocked and deployed.
# The `reverts` context manager is from `brownie.reverts`.
# `tx.events` is a Brownie feature for inspecting events from transactions.
# `chain.time()` and `chain.sleep()` are Brownie's way to manipulate block time.
# `accounts[0]` is admin, `accounts[1]` is session_creator etc.
# These tests are structured for a Brownie environment.
# The placeholder MockERC20 and MockERC721 would need to be replaced with actual
# Solidity mock contracts deployed in your Brownie project for these tests to run properly.
# For example, using OpenZeppelin's TestContracts: ERC20Mock.sol, ERC721Mock.sol.
# The current mock setup is a simplification due to not having .sol files for mocks.
# A real setup:
# 1. Add MockERC20.sol, MockERC721.sol to your contracts/test folder.
# 2. In fixtures: `token = admin.deploy(project.MockERC20, ...)`
# 3. Then calls like `usdc_token.approve(...)` would work on these deployed mocks.
# 4. Balance checks: `assert usdc_token.balanceOf(user_one) == initial_balance - fee`
# The current tests will likely fail if run directly without these .sol mocks
# and adjustments to the fixtures to deploy them.
# The focus here is on the structure and intent of the tests for CalculusEngine.sol.
