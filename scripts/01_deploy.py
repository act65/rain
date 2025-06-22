# File: scripts/01_deploy.py (Corrected)

from brownie import (
    accounts,
    CurrencyToken,
    ReputationSBT,
    LoanContract,
    InsuranceDAO,
    # New contract imports
    ReputationV2,
    OfflineToken,
    RainfallPool,
    Jury,
    Treasury,
)
import json

# --- CONFIGURATION ---
INITIAL_REPUTATION = 100
INITIAL_CURRENCY_MINT = 5000 # Per user
INSURANCE_QUORUM = 150 # Example value for InsuranceDAO (weighted by reputation)
DEPLOYMENT_FILE = "deployment_addresses.json"

# New configurations for Jury and Treasury
MIN_JUROR_STAKE = 100 * (10**18) # Assuming USDC (CurrencyToken) has 18 decimals
VOTING_PERIOD_DURATION = 3 * 24 * 60 * 60 # 3 days in seconds
QUORUM_PERCENTAGE = 10 * (10**16) # 10% (0.1 * 1e18)
DECISION_THRESHOLD_PERCENTAGE = 51 * (10**16) # 51% (0.51 * 1e18)

MIN_AMOUNT_FOR_NEW_TREASURY_CYCLE = 100 * (10**18) # 100 USDC
TREASURY_CLAIM_PERIOD_DURATION = 30 * 24 * 60 * 60 # 30 days in seconds


def main():
    """
    Deploys all contracts, configures them, mints initial tokens,
    and saves the addresses to a file.
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

    # --- 2. DEPLOY CORE CONTRACTS (Currency and New ReputationV2) ---
    print("Deploying core contracts (CurrencyToken, ReputationV2)...")
    currency_token = CurrencyToken.deploy({"from": deployer})
    # Deploy ReputationV2 instead of ReputationSBT directly
    reputation_v2 = ReputationV2.deploy({"from": deployer})
    print(f"CurrencyToken (DMD) deployed at: {currency_token.address}")
    print(f"ReputationV2 (REPV2) deployed at: {reputation_v2.address}\n")

    # --- 3. DEPLOY NEW FEATURE CONTRACTS ---
    print("Deploying new feature contracts (OfflineToken, RainfallPool, Jury, Treasury)...")
    offline_token = OfflineToken.deploy(reputation_v2.address, {"from": deployer})
    print(f"OfflineToken deployed at: {offline_token.address}")

    rainfall_pool = RainfallPool.deploy(currency_token.address, {"from": deployer})
    print(f"RainfallPool deployed at: {rainfall_pool.address}")

    jury_contract = Jury.deploy(
        currency_token.address,
        offline_token.address,
        MIN_JUROR_STAKE,
        VOTING_PERIOD_DURATION,
        QUORUM_PERCENTAGE,
        DECISION_THRESHOLD_PERCENTAGE,
        {"from": deployer},
    )
    print(f"Jury contract deployed at: {jury_contract.address}")

    treasury_contract = Treasury.deploy(
        reputation_v2.address,
        currency_token.address,
        MIN_AMOUNT_FOR_NEW_TREASURY_CYCLE,
        TREASURY_CLAIM_PERIOD_DURATION,
        {"from": deployer},
    )
    print(f"Treasury contract deployed at: {treasury_contract.address}\n")

    # --- 4. DEPLOY UPDATED EXISTING APPLICATION LOGIC CONTRACTS ---
    # LoanContract and InsuranceDAO now use ReputationV2
    print("Deploying updated application logic contracts (LoanContract, InsuranceDAO)...")
    loan_contract = LoanContract.deploy(
        currency_token.address, reputation_v2.address, {"from": deployer} # Use ReputationV2
    )
    insurance_dao = InsuranceDAO.deploy(
        currency_token.address,
        reputation_v2.address, # Use ReputationV2
        INSURANCE_QUORUM,
        {"from": deployer},
    )
    print(f"LoanContract deployed at: {loan_contract.address}")
    print(f"InsuranceDAO deployed at: {insurance_dao.address}\n")

    # --- 5. CONFIGURE PERMISSIONS AND LINKS ---
    print("Configuring contract permissions and links...")
    # LoanContract and InsuranceDAO need to be trusted by ReputationV2
    reputation_v2.setTrustedContract(loan_contract.address, True, {"from": deployer})
    reputation_v2.setTrustedContract(insurance_dao.address, True, {"from": deployer})

    # OfflineToken needs to be trusted by ReputationV2 to call stake/slash
    reputation_v2.setTrustedContract(offline_token.address, True, {"from": deployer})

    # Jury contract needs to be set in OfflineToken to allow slashing
    offline_token.setJuryContract(jury_contract.address, {"from": deployer})

    # If Jury contract itself needs to be a trusted contract in ReputationV2 (e.g., if it directly adjusted reputation)
    # reputation_v2.setTrustedContract(jury_contract.address, True, {"from": deployer})
    # Currently, Jury calls OfflineToken.slashStake, which then calls ReputationV2.slash. So direct trust might not be needed for Jury on RepV2.

    print("Permissions and links set successfully.\n")

    # --- 6. MINT INITIAL ASSETS FOR USERS ---
    print("Minting initial assets for Alice, Bob, and Charlie...")
    users = {"Alice": alice, "Bob": bob, "Charlie": charlie}
    for name, account in users.items():
        # Mint Currency Tokens
        currency_token.mint(account.address, INITIAL_CURRENCY_MINT * (10**18), {"from": deployer}) # Assuming 18 decimals for DMD

        # Mint ReputationV2 tokens (SBTs)
        rep = INITIAL_REPUTATION * 2 if name == "Alice" else INITIAL_REPUTATION
        reputation_v2.mint(account.address, rep, {"from": deployer})
        print(f"  - Minted assets for {name} ({account.address}): {INITIAL_CURRENCY_MINT} DMD, {rep} REPV2.")

    # --- 7. SAVE DEPLOYMENT ADDRESSES ---
    print(f"\nSaving deployment addresses to {DEPLOYMENT_FILE}...")
    deployment_data = {
        "CurrencyToken": currency_token.address,
        "ReputationV2": reputation_v2.address, # Changed from ReputationSBT
        "OfflineToken": offline_token.address,
        "RainfallPool": rainfall_pool.address,
        "Jury": jury_contract.address,
        "Treasury": treasury_contract.address,
        "LoanContract": loan_contract.address, # Still deployed, now using ReputationV2
        "InsuranceDAO": insurance_dao.address, # Still deployed, now using ReputationV2
    }
    with open(DEPLOYMENT_FILE, "w") as f:
        json.dump(deployment_data, f, indent=4)

    print("\nDeployment and setup complete!")