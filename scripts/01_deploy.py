# File: scripts/01_deploy.py (Corrected)

from brownie import (
    accounts,
    CurrencyToken,
    ReputationSBT,
    LoanContract,
    InsuranceDAO,
)
import json

# --- CONFIGURATION ---
INITIAL_REPUTATION = 100
INITIAL_CURRENCY_MINT = 5000
INSURANCE_QUORUM = 150
DEPLOYMENT_FILE = "deployment_addresses.json"


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

    # --- 2. DEPLOY CORE CONTRACTS ---
    print("Deploying core contracts...")
    currency_token = CurrencyToken.deploy({"from": deployer})
    reputation_sbt = ReputationSBT.deploy({"from": deployer})
    print(f"CurrencyToken (DMD) deployed at: {currency_token.address}")
    print(f"ReputationSBT (REPSBT) deployed at: {reputation_sbt.address}\n")

    # --- 3. DEPLOY APPLICATION LOGIC CONTRACTS ---
    print("Deploying application logic contracts...")
    loan_contract = LoanContract.deploy(
        currency_token.address, reputation_sbt.address, {"from": deployer}
    )
    insurance_dao = InsuranceDAO.deploy(
        currency_token.address,
        reputation_sbt.address,
        INSURANCE_QUORUM,
        {"from": deployer},
    )
    print(f"LoanContract deployed at: {loan_contract.address}")
    print(f"InsuranceDAO deployed at: {insurance_dao.address}\n")

    # --- 4. CONFIGURE PERMISSIONS ---
    print("Configuring contract permissions...")
    reputation_sbt.setTrustedContract(loan_contract.address, True, {"from": deployer})
    reputation_sbt.setTrustedContract(insurance_dao.address, True, {"from": deployer})
    print("Permissions set successfully.\n")

    # --- 5. MINT INITIAL ASSETS FOR USERS ---
    print("Minting initial assets for Alice, Bob, and Charlie...")
    users = {"Alice": alice, "Bob": bob, "Charlie": charlie}
    for name, account in users.items():
        currency_token.mint(account, INITIAL_CURRENCY_MINT, {"from": deployer})
        rep = INITIAL_REPUTATION * 2 if name == "Alice" else INITIAL_REPUTATION
        reputation_sbt.mint(account, rep, {"from": deployer})
        print(f"  - Minted assets for {name} with {rep} reputation.")

    # --- 6. SAVE DEPLOYMENT ADDRESSES ---
    print(f"\nSaving deployment addresses to {DEPLOYMENT_FILE}...")
    deployment_data = {
        "CurrencyToken": currency_token.address,
        "ReputationSBT": reputation_sbt.address,
        "LoanContract": loan_contract.address,
        "InsuranceDAO": insurance_dao.address,
    }
    with open(DEPLOYMENT_FILE, "w") as f:
        json.dump(deployment_data, f, indent=4)

    print("\nDeployment and setup complete!")