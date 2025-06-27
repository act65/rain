import pytest
from brownie import (
    accounts,
    CalculusEngine,
    CurrencyToken,
    RainReputation,
    ReputationClaimToken
)

# Re-usable accounts
@pytest.fixture(scope="session")
def deployer():
    return accounts[0]

@pytest.fixture(scope="session")
def treasury():
    return accounts[1]

@pytest.fixture(scope="session")
def user_alice():
    return accounts[2]

@pytest.fixture(scope="session")
def user_bob():
    return accounts[3]

@pytest.fixture(scope="session")
def script_contract_owner():
    # This will be the address that is granted SESSION_CREATOR_ROLE
    return accounts[4]

# NEW: Add an account for a second, "malicious" script
@pytest.fixture(scope="session")
def malicious_script_owner():
    return accounts[5]


# A fixture that deploys a full suite of contracts for integration testing
@pytest.fixture(scope="module")
def contracts(deployer, treasury, user_alice, user_bob, script_contract_owner, malicious_script_owner): # <- Add new account
    """
    Deploys all core contracts and sets up initial state and roles.
    This fixture has a 'module' scope, so it only runs once per test file.
    """
    # 1. Deploy mock USDC token and mint some to Alice
    currency_token = CurrencyToken.deploy({'from': deployer})
    mint_amount = 1_000_000 * 10**currency_token.decimals()
    currency_token.mint(user_alice, mint_amount, {'from': deployer})

    # 2. Deploy the CalculusEngine
    initial_fee = 100 * 10**currency_token.decimals() # e.g., 100 USDC
    calculus_engine = CalculusEngine.deploy(
        currency_token.address,
        treasury.address,
        initial_fee,
        {'from': deployer}
    )

    # 3. Grant the SESSION_CREATOR_ROLE to our designated script owner account
    session_creator_role = calculus_engine.SESSION_CREATOR_ROLE()
    calculus_engine.grantRole(session_creator_role, script_contract_owner, {'from': deployer})

    # 4. Deploy Reputation contracts (needed for RCT tests later)
    reputation_contract = RainReputation.deploy({'from': deployer})
    rct_contract = ReputationClaimToken.deploy(reputation_contract.address, {'from': deployer})

    # Return a dictionary of contracts and key addresses for easy access in tests
    return {
        "calculus_engine": calculus_engine,
        "currency_token": currency_token,
        "reputation_contract": reputation_contract,
        "rct_contract": rct_contract,
        "deployer": deployer,
        "treasury": treasury,
        "user_alice": user_alice,
        "user_bob": user_bob,
        "script_contract_owner": script_contract_owner,
        "malicious_script_owner": malicious_script_owner, # <- Add new account to dict
        "initial_fee": initial_fee
    }