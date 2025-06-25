# File: scripts/02_simulate_loan.py (Corrected for the Atomic Action Framework)

from brownie import (
    accounts,
    chain,
    LoanScript,
    CalculusEngine,
    CurrencyToken,
    RainReputation,
    ReputationClaimToken,
)
import json
import time

DEPLOYMENT_FILE = "deployment_addresses.json"

def main():
    """
    Simulates the loan cycle by deploying and interacting with a LoanScript
    that uses the core protocol primitives.
    """
    # --- 1. SETUP ---
    print("--- LOAN SIMULATION (ATOMIC ACTION FRAMEWORK) ---")

    # Load accounts
    deployer = accounts[0]
    alice = accounts[1] # Lender
    bob = accounts[2]   # Borrower (Happy Path)
    charlie = accounts[3] # Borrower (Unhappy Path)

    # Load contract addresses from the deployment file
    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

    # Create contract objects for the core protocol
    calculus_engine = CalculusEngine.at(addresses["CalculusEngine"])
    currency_token = CurrencyToken.at(addresses["CurrencyToken"])
    rain_reputation = RainReputation.at(addresses["RainReputation"])
    rct_contract = ReputationClaimToken.at(addresses["ReputationClaimToken"])

    # Deploy the LoanScript application
    print("\nDeploying the LoanScript application...")
    loan_script = LoanScript.deploy(
        calculus_engine.address,
        rain_reputation.address,
        rct_contract.address,
        currency_token.address,
        {"from": deployer},
    )
    print(f"LoanScript deployed at: {loan_script.address}")

    # Grant the LoanScript permission to mint RCTs on default
    minter_role = rct_contract.MINTER_ROLE()
    rct_contract.grantRole(minter_role, loan_script.address, {"from": deployer})
    print("Granted MINTER_ROLE to LoanScript.\n")


    # --- 2. HAPPY PATH SIMULATION: Bob borrows from Alice ---
    print("\n--- Starting Happy Path: Bob borrows from Alice ---")
    principal = 1000 * (10**18)
    interest = 50 * (10**18)
    duration_seconds = 60 * 60 * 24 * 30 # 30 days
    reputation_stake = 50 * (10**18)

    print(f"Initial Reputation - Bob: {rain_reputation.reputationScores(bob) / 10**18}")
    print(f"Initial Balance - Alice: {currency_token.balanceOf(alice) / 10**18}, Bob: {currency_token.balanceOf(bob) / 10**18}")

    print("\nStep A: Bob requests a loan via the LoanScript...")
    # Bob pays the fee to the CalculusEngine, so no approval is needed here.
    tx_req = loan_script.requestLoan(alice.address, principal, interest, duration_seconds, reputation_stake, {"from": bob})
    loan_id = tx_req.events["LoanRequested"]["loanId"]
    print(f"  - Loan {loan_id} requested.")
    print(f"  - Bob's Staked Reputation: {rain_reputation.stakedReputation(bob) / 10**18}")

    print("\nStep B: Alice funds the loan...")
    # Alice must approve the CALCULUS ENGINE to transfer her funds, as it executes the transfer.
    currency_token.approve(calculus_engine.address, principal, {"from": alice})
    loan_script.fundLoan(loan_id, {"from": alice})
    print(f"  - Loan funded. Bob's balance: {currency_token.balanceOf(bob) / 10**18}, Alice's balance: {currency_token.balanceOf(alice) / 10**18}")

    print("\nStep C: Bob repays the loan...")
    # Bob must approve the CALCULUS ENGINE for the full repayment amount.
    repayment_amount = principal + interest
    currency_token.approve(calculus_engine.address, repayment_amount, {"from": bob})
    loan_script.repayLoan(loan_id, {"from": bob})
    print("  - Loan repaid.")

    print("\nHappy Path Final State:")
    print(f"  - Bob's Reputation: {rain_reputation.reputationScores(bob) / 10**18}")
    print(f"  - Bob's Staked Reputation: {rain_reputation.stakedReputation(bob) / 10**18} (should be 0)")
    print(f"  - Bob's Balance: {currency_token.balanceOf(bob) / 10**18}")
    print(f"  - Alice's Balance: {currency_token.balanceOf(alice) / 10**18}")
    print(f"  - Loan {loan_id} Status Code: {loan_script.loans(loan_id)[6]} (2 means Repaid)")


    # --- 3. UNHAPPY PATH SIMULATION: Charlie borrows from Alice and defaults ---
    print("\n\n--- Starting Unhappy Path: Charlie borrows from Alice and defaults ---")
    print(f"Initial Reputation - Charlie: {rain_reputation.reputationScores(charlie) / 10**18}")

    print("\nStep A: Charlie requests a loan...")
    tx_req_def = loan_script.requestLoan(alice.address, principal, interest, duration_seconds, reputation_stake, {"from": charlie})
    default_loan_id = tx_req_def.events["LoanRequested"]["loanId"]
    print(f"  - Loan {default_loan_id} requested. Charlie's staked reputation: {rain_reputation.stakedReputation(charlie) / 10**18}")

    print("\nStep B: Alice funds the loan...")
    currency_token.approve(calculus_engine.address, principal, {"from": alice})
    loan_script.fundLoan(default_loan_id, {"from": alice})
    print("  - Loan funded.")

    print("\nStep C: Simulating time passing beyond the deadline...")
    chain.sleep(duration_seconds + 1)
    chain.mine()
    print("  - Time elapsed.")

    print("\nStep D: Alice claims the default...")
    tx_def = loan_script.claimDefault(default_loan_id, {"from": alice})
    rct_id = tx_def.events["LoanDefaulted"]["rctId"]
    print(f"  - Default claimed. RCT with ID {rct_id} was minted to Alice.")

    print("\nUnhappy Path Final State:")
    print(f"  - Charlie's Staked Reputation: {rain_reputation.stakedReputation(charlie) / 10**18} (should still be staked)")
    print(f"  - Loan {default_loan_id} Status Code: {loan_script.loans(default_loan_id)[6]} (3 means Defaulted)")
    print(f"  - Owner of RCT {rct_id}: {rct_contract.ownerOf(rct_id)}")
    print(f"  - Alice's Address: {alice.address}")
    assert rct_contract.ownerOf(rct_id) == alice.address
    print("  - VERIFIED: Alice is the owner of the new RCT.")
    print("\nNOTE: Charlie's reputation has not been slashed yet. That is the asynchronous job of the off-chain oracle.")