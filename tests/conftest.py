import pytest
from helpers import E18, accounts, deploy_reputation, deploy_system, project

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
    # An account that plays the part of a script contract
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
    currency_token = project.CurrencyToken.deploy(sender=deployer)
    mint_amount = 1_000_000 * 10**currency_token.decimals()
    currency_token.mint(user_alice, mint_amount, sender=deployer)

    # 2. Deploy the CalculusEngine with a flat fee (no proportional part) and a point price of 1
    initial_fee = 100 * 10**currency_token.decimals() # e.g., 100 USDC
    calculus_engine = project.CalculusEngine.deploy(
        currency_token.address, treasury.address, 0, initial_fee, E18, sender=deployer
    )

    # 3. Deploy Reputation contracts (no decay). No roles are needed to act as a script:
    #    `script_contract_owner` and `malicious_script_owner` are simply accounts.
    reputation_contract = deploy_reputation(deployer)
    rct_contract = project.ReputationClaimToken.deploy(reputation_contract.address, calculus_engine.address, sender=deployer)
    reputation_contract.setRctContract(rct_contract.address, sender=deployer)

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

# Ape isolates tests from each other: the chain is restored after every test to the state
# left by the module-scoped fixtures.

@pytest.fixture(scope="module")
def system():
    """
    The whole protocol with round numbers: a flat fee of 1 DMD per promise, 25 points earned
    per kept promise (`system.reward`), no decay, a Treasury that shares out its whole fund each
    cycle with no waiting between cycles, and 1,000 points each for Alice, Bob and Carol.
    Tests of proportional fees, decay and gradual payout deploy their own.
    """
    return deploy_system()
