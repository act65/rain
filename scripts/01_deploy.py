# File: scripts/01_deploy.py (Corrected for the Atomic Action Framework)

from brownie import (
    accounts,
    CurrencyToken,
    RainReputation,
    ReputationClaimToken,
    CalculusEngine,
    ReputationUpdater,
    TreasuryV2,
)
import json

# --- CONFIGURATION ---
INITIAL_REPUTATION = 100 * (10**18)
INITIAL_CURRENCY_MINT = 5000 * (10**18) # Assuming 18 decimals
DEPLOYMENT_FILE = "deployment_addresses.json"

# New configurations for the final architecture
CALCULUS_ENGINE_FEE = 1 * (10**17) # 0.1 DMD (assuming 18 decimals)
TREASURY_CLAIM_PERIOD = 30 * 24 * 60 * 60 # 30 days in seconds


def main():
    """
    Deploys all contracts for the Atomic Action Framework, configures their roles
    and permissions, mints initial tokens, and saves addresses to a file.
    """
    # --- 1. SETUP ACCOUNTS ---
    deployer = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    charlie = accounts[3]
    
    print(f"Deployer: {deployer.address}")
    print(f"Alice: {alice.address}")
    print(f"Bob: {bob.address}")
    print(f"Charlie: {charlie.address}\n")

    # --- 2. DEPLOY CORE CONTRACTS ---
    print("Deploying core contracts...")
    currency_token = CurrencyToken.deploy({"from": deployer})
    print(f"CurrencyToken (DMD) deployed at: {currency_token.address}")

    rain_reputation = RainReputation.deploy({"from": deployer})
    print(f"RainReputation (RAIN) deployed at: {rain_reputation.address}")

    # --- 3. DEPLOY PRIMITIVE & ENGINE CONTRACTS ---
    print("\nDeploying protocol engine contracts...")
    rct_contract = ReputationClaimToken.deploy(rain_reputation.address, {"from": deployer})
    print(f"ReputationClaimToken (RCT) deployed at: {rct_contract.address}")

    treasury_v2 = TreasuryV2.deploy(currency_token.address, TREASURY_CLAIM_PERIOD, {"from": deployer})
    print(f"TreasuryV2 deployed at: {treasury_v2.address}")

    calculus_engine = CalculusEngine.deploy(
        currency_token.address,
        treasury_v2.address,
        CALCULUS_ENGINE_FEE,
        {"from": deployer},
    )
    print(f"CalculusEngine deployed at: {calculus_engine.address}")

    reputation_updater = ReputationUpdater.deploy(rain_reputation.address, {"from": deployer})
    print(f"ReputationUpdater deployed at: {reputation_updater.address}\n")

    # --- 4. CONFIGURE ROLES AND PERMISSIONS ---
    print("Configuring contract roles and permissions...")

    # Grant ReputationUpdater the right to update scores in RainReputation
    updater_role = rain_reputation.UPDATER_ROLE()
    rain_reputation.grantRole(updater_role, reputation_updater.address, {"from": deployer})
    print(f" - Granted UPDATER_ROLE on RainReputation to ReputationUpdater.")

    # Set the RCT contract address in RainReputation so it can set delinquent status
    rain_reputation.setRctContract(rct_contract.address, {"from": deployer})
    print(f" - Set RCT contract address in RainReputation.")

    # For simulation, grant the deployer account roles that would normally belong
    # to scripts or specialized bots.

    # Grant deployer the right to create sessions in CalculusEngine (acting as a script)
    session_creator_role = calculus_engine.SESSION_CREATOR_ROLE()
    calculus_engine.grantRole(session_creator_role, deployer.address, {"from": deployer})
    print(f" - Granted SESSION_CREATOR_ROLE on CalculusEngine to deployer (for simulation).")

    # Grant deployer the right to call the ReputationUpdater (acting as the oracle)
    updater_role_on_updater = reputation_updater.UPDATER_ROLE()
    reputation_updater.grantRole(updater_role_on_updater, deployer.address, {"from": deployer})
    print(f" - Granted UPDATER_ROLE on ReputationUpdater to deployer (for simulation).")

    # Grant deployer the right to manage the Treasury
    manager_role = treasury_v2.MANAGER_ROLE()
    treasury_v2.grantRole(manager_role, deployer.address, {"from": deployer})
    print(f" - Granted MANAGER_ROLE on TreasuryV2 to deployer.")

    # Grant deployer the right to mint RCTs (acting as a LoanScript)
    minter_role = rct_contract.MINTER_ROLE()
    rct_contract.grantRole(minter_role, deployer.address, {"from": deployer})
    print(f" - Granted MINTER_ROLE on ReputationClaimToken to deployer (for simulation).")

    print("\nPermissions and roles configured successfully.\n")

    # --- 5. MINT INITIAL ASSETS FOR USERS ---
    print("Minting initial assets for Alice, Bob, and Charlie...")
    users = {"Alice": alice, "Bob": bob, "Charlie": charlie}
    for name, account in users.items():
        # Mint Currency Tokens
        currency_token.mint(account.address, INITIAL_CURRENCY_MINT, {"from": deployer})

        # Mint Reputation SBTs and set initial score
        rep = INITIAL_REPUTATION * 2 if name == "Alice" else INITIAL_REPUTATION
        rain_reputation.mint(account.address, rep, {"from": deployer})
        print(f"  - Minted assets for {name} ({account.address}): {INITIAL_CURRENCY_MINT / 10**18} DMD, {rep / 10**18} RAIN.")

    # --- 6. SAVE DEPLOYMENT ADDRESSES ---
    print(f"\nSaving deployment addresses to {DEPLOYMENT_FILE}...")
    deployment_data = {
        "CurrencyToken": currency_token.address,
        "RainReputation": rain_reputation.address,
        "ReputationClaimToken": rct_contract.address,
        "CalculusEngine": calculus_engine.address,
        "ReputationUpdater": reputation_updater.address,
        "TreasuryV2": treasury_v2.address,
    }
    with open(DEPLOYMENT_FILE, "w") as f:
        json.dump(deployment_data, f, indent=4)

    print("\nDeployment and setup complete!")