# File: scripts/02_simulate_loan.py (Corrected)

from brownie import (
    accounts,
    chain,
    LoanContract,
    CurrencyToken,
    ReputationSBT,
)
import json
import time

DEPLOYMENT_FILE = "deployment_addresses.json"

def main():
    """
    Simulates the loan cycle by loading contract addresses from a file.
    """
    # --- 1. SETUP ---
    print("--- LOAN SIMULATION ---")
    
    # Load contract addresses from the file
    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

    # Create contract objects from the ABIs Brownie has compiled
    # using the addresses from our deployment file.
    loan_contract = LoanContract.at(addresses["LoanContract"])
    currency_token = CurrencyToken.at(addresses["CurrencyToken"])
    reputation_sbt = ReputationSBT.at(addresses["ReputationSBT"])

    # Get users
    alice = accounts[1]
    bob = accounts[2]
    charlie = accounts[3]

    # --- THE REST OF THE SCRIPT IS IDENTICAL ---

    # --- 2. HAPPY PATH SIMULATION ---
    print("\n--- Starting Happy Path: Alice borrows from Bob ---")
    principal = 1000
    interest = 50
    repayment_period_seconds = 60 * 60 * 24 * 30
    print(f"Initial Reputation - Alice: {reputation_sbt.reputationScores(alice)}")
    print(f"Initial Balance - Alice: {currency_token.balanceOf(alice)}, Bob: {currency_token.balanceOf(bob)}")
    print("\nStep A: Alice requests a loan...")
    loan_contract.requestLoan(principal, interest, repayment_period_seconds, {"from": alice})
    loan_id = loan_contract.nextLoanId() - 1
    print(f"  - Loan {loan_id} requested. Alice's staked reputation: {reputation_sbt.stakedReputation(alice)}")
    print("\nStep B: Bob funds the loan...")
    currency_token.approve(loan_contract.address, principal, {"from": bob})
    loan_contract.fundLoan(loan_id, {"from": bob})
    print(f"  - Loan funded. Alice's balance: {currency_token.balanceOf(alice)}, Bob's balance: {currency_token.balanceOf(bob)}")
    print("\nStep C: Alice repays the loan...")
    currency_token.approve(loan_contract.address, principal + interest, {"from": alice})
    loan_contract.repayLoan(loan_id, {"from": alice})
    print("  - Loan repaid.")
    print("\nHappy Path Final State:")
    print(f"  - Alice's Reputation: {reputation_sbt.reputationScores(alice)}")
    print(f"  - Alice's Staked Reputation: {reputation_sbt.stakedReputation(alice)}")
    print(f"  - Alice's Balance: {currency_token.balanceOf(alice)}")
    print(f"  - Bob's Balance: {currency_token.balanceOf(bob)}")
    print(f"  - Loan {loan_id} Status: {loan_contract.loans(loan_id)[7]}")

    # --- 3. UNHAPPY PATH SIMULATION ---
    print("\n\n--- Starting Unhappy Path: Charlie borrows from Bob and defaults ---")
    print(f"Initial Reputation - Charlie: {reputation_sbt.reputationScores(charlie)}")
    print("\nStep A: Charlie requests a loan...")
    loan_contract.requestLoan(principal, interest, repayment_period_seconds, {"from": charlie})
    default_loan_id = loan_contract.nextLoanId() - 1
    print(f"  - Loan {default_loan_id} requested. Charlie's staked reputation: {reputation_sbt.stakedReputation(charlie)}")
    print("\nStep B: Bob funds the loan...")
    currency_token.approve(loan_contract.address, principal, {"from": bob})
    loan_contract.fundLoan(default_loan_id, {"from": bob})
    print("  - Loan funded.")
    print("\nStep C: Simulating time passing...")
    chain.sleep(repayment_period_seconds + 1)
    chain.mine()
    print("  - Time elapsed.")
    print("\nStep D: Bob claims the default...")
    loan_contract.claimDefault(default_loan_id, {"from": bob})
    print("  - Default claimed.")
    print("\nUnhappy Path Final State:")
    print(f"  - Charlie's Reputation: {reputation_sbt.reputationScores(charlie)}")
    print(f"  - Charlie's Staked Reputation: {reputation_sbt.stakedReputation(charlie)}")
    print(f"  - Loan {default_loan_id} Status: {loan_contract.loans(default_loan_id)[7]}")