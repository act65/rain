# File: scripts/deploy.py

from ape import accounts, project

from rain.utils import save_deployment_data

# --- CONFIGURATION ---
E18 = 10**18
INITIAL_CURRENCY_MINT = 5000 * E18 # Assuming 18 decimals
DEPLOYMENT_FILE = "deployment_addresses.json"
PERIOD = 30 * 24 * 60 * 60 # 30 days in seconds

# Fees: 1% of the amount promised, at least 0.1 DMD.
FEE_BPS = 100
MIN_FEE = E18 // 10
# Reputation costs 0.04 DMD of fees per point (so a 1 DMD fee earns 25 points).
POINT_PRICE = 4 * E18 // 100
# Reputation loses 3% every 30 days (a half-life of about two years).
DECAY_PERIOD = PERIOD
RETENTION_PER_PERIOD = 97 * E18 // 100
# The Treasury pays fees out gradually: each dividend cycle shares out a fraction of its payout
# fund equal to the reputation decay, one cycle per decay period. Dividends then follow fee
# income at the speed the supply of reputation does, so a point is never worth more than it cost.
RELEASE_PER_CYCLE = E18 - RETENTION_PER_PERIOD
CYCLE_INTERVAL = DECAY_PERIOD
TREASURY_CLAIM_PERIOD = PERIOD


def main():
    """
    Deploys all core contracts, configures their roles, mints initial tokens,
    and saves addresses to a file.
    """
    # --- 1. SETUP ACCOUNTS ---
    deployer = accounts.test_accounts[0]
    alice = accounts.test_accounts[1]
    bob = accounts.test_accounts[2]
    charlie = accounts.test_accounts[3]

    print(f"Deployer: {deployer.address}")
    print(f"Alice: {alice.address}")
    print(f"Bob: {bob.address}")
    print(f"Charlie: {charlie.address}\n")

    # --- 2. DEPLOY CORE CONTRACTS ---
    print("Deploying core contracts...")
    currency_token = project.CurrencyToken.deploy(sender=deployer)
    print(f"CurrencyToken (DMD) deployed at: {currency_token.address}")

    treasury = project.Treasury.deploy(
        currency_token.address, TREASURY_CLAIM_PERIOD, RELEASE_PER_CYCLE, CYCLE_INTERVAL, sender=deployer
    )
    print(f"Treasury deployed at: {treasury.address}")

    rain_reputation = project.RainReputation.deploy(DECAY_PERIOD, RETENTION_PER_PERIOD, sender=deployer)
    print(f"RainReputation (RAIN) deployed at: {rain_reputation.address}")

    # --- 3. DEPLOY PRIMITIVE & ENGINE CONTRACTS ---
    print("\nDeploying protocol engine contracts...")
    calculus_engine = project.CalculusEngine.deploy(
        currency_token.address, treasury.address, FEE_BPS, MIN_FEE, POINT_PRICE, sender=deployer
    )
    print(f"CalculusEngine deployed at: {calculus_engine.address}")

    rct_contract = project.ReputationClaimToken.deploy(
        rain_reputation.address, calculus_engine.address, sender=deployer
    )
    print(f"ReputationClaimToken (RCT) deployed at: {rct_contract.address}")

    reputation_updater = project.ReputationUpdater.deploy(rain_reputation.address, sender=deployer)
    print(f"ReputationUpdater deployed at: {reputation_updater.address}\n")

    # --- 4. CONFIGURE ROLES AND PERMISSIONS ---
    print("Configuring contract roles and permissions...")

    # Grant ReputationUpdater the right to update scores in RainReputation
    rain_reputation.grantRole(rain_reputation.UPDATER_ROLE(), reputation_updater.address, sender=deployer)
    print(" - Granted UPDATER_ROLE on RainReputation to ReputationUpdater.")

    # Set the RCT contract address in RainReputation so it can set delinquent status
    rain_reputation.setRctContract(rct_contract.address, sender=deployer)
    print(" - Set RCT contract address in RainReputation.")

    # For simulation, the deployer account plays the roles that would normally
    # belong to specialized bots (the oracle and the treasury manager).
    # Scripts need no role: anyone can deploy one.

    # Grant deployer the right to call the ReputationUpdater (acting as the oracle)
    reputation_updater.grantRole(reputation_updater.UPDATER_ROLE(), deployer.address, sender=deployer)
    print(" - Granted UPDATER_ROLE on ReputationUpdater to deployer (for simulation).")

    # The deployer already manages the Treasury (the constructor grants MANAGER_ROLE).
    print("\nPermissions and roles configured successfully.\n")

    # --- 5. MINT INITIAL ASSETS FOR USERS ---
    print("Minting initial assets for Alice, Bob, and Charlie...")
    users = {"Alice": alice, "Bob": bob, "Charlie": charlie}
    for name, account in users.items():
        currency_token.mint(account.address, INITIAL_CURRENCY_MINT, sender=deployer)

        # Issue the identity token. A new identity holds no reputation: it is earned by keeping promises.
        rain_reputation.mint(account.address, sender=deployer)
        print(f"  - Minted for {name} ({account.address}): {INITIAL_CURRENCY_MINT / 10**18} DMD and an identity.")

    # --- 6. SAVE DEPLOYMENT ADDRESSES ---
    print(f"\nSaving deployment addresses to {DEPLOYMENT_FILE}...")
    deployment_data = {
        "CurrencyToken": currency_token.address,
        "RainReputation": rain_reputation.address,
        "ReputationClaimToken": rct_contract.address,
        "CalculusEngine": calculus_engine.address,
        "ReputationUpdater": reputation_updater.address,
        "Treasury": treasury.address,
    }
    save_deployment_data(deployment_data, DEPLOYMENT_FILE)

    print("\nDeployment and setup complete!")
