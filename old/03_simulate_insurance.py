# File: scripts/03_simulate_insurance.py (Corrected)

from brownie import (
    accounts,
    InsuranceDAO,
    CurrencyToken,
    ReputationV2, # Changed from ReputationSBT
)
import json

DEPLOYMENT_FILE = "deployment_addresses.json"

def main():
    """
    Simulates the DAO Insurance Pool by loading contract addresses from a file.
    """
    print("--- INSURANCE DAO SIMULATION ---")
    # --- 1. SETUP ---
    with open(DEPLOYMENT_FILE) as f:
        addresses = json.load(f)

    insurance_dao = InsuranceDAO.at(addresses["InsuranceDAO"])
    currency_token = CurrencyToken.at(addresses["CurrencyToken"])
    reputation_v2 = ReputationV2.at(addresses["ReputationV2"]) # Changed variable name and contract type

    # Get users
    alice = accounts[1]
    bob = accounts[2]
    charlie = accounts[3]

    # --- THE REST OF THE SCRIPT IS IDENTICAL ---
    
    # --- 2. POOL CONTRIBUTION ---
    print("\n--- Step 1: Users contribute to the insurance pool ---")
    alice_rep = reputation_v2.getEffectiveReputation(alice) # Changed to reputation_v2 and getEffectiveReputation
    bob_rep = reputation_v2.getEffectiveReputation(bob) # Changed to reputation_v2 and getEffectiveReputation
    charlie_rep = reputation_v2.getEffectiveReputation(charlie) # Changed to reputation_v2 and getEffectiveReputation
    print(f"Reputation Scores -> Alice: {alice_rep}, Bob: {bob_rep}, Charlie: {charlie_rep}")
    contribution_amount = 500
    for user in [alice, bob, charlie]:
        currency_token.approve(insurance_dao.address, contribution_amount, {"from": user})
        insurance_dao.contribute(contribution_amount, {"from": user})
    print(f"  - Alice, Bob, and Charlie each contributed {contribution_amount} DMD.")
    print(f"  - Insurance DAO Pool Balance: {currency_token.balanceOf(insurance_dao.address)}")

    # --- 3. CLAIM AND VOTING ---
    print("\n--- Step 2: Charlie submits a claim ---")
    claim_amount = 250
    claim_description = "My bike was stolen"
    insurance_dao.submitClaim(claim_amount, claim_description, {"from": charlie})
    claim_id = insurance_dao.nextClaimId() - 1
    print(f"  - Charlie submitted Claim {claim_id} for {claim_amount} DMD.")

    print("\n--- Step 3: Members vote on the claim ---")
    quorum = insurance_dao.approvalQuorum()
    print(f"  - Approval Quorum is {quorum} weighted votes.")
    insurance_dao.voteOnClaim(claim_id, True, {"from": alice})
    claim_status = insurance_dao.claims(claim_id)
    print(f"  - Alice (Reputation: {alice_rep}) voted YES. Approval votes: {claim_status[5]}")
    insurance_dao.voteOnClaim(claim_id, False, {"from": bob})
    claim_status = insurance_dao.claims(claim_id)
    print(f"  - Bob (Reputation: {bob_rep}) voted NO. Rejection votes: {claim_status[6]}")
    print(f"  - Final Claim Status Code: {claim_status[4]}")

    # --- 4. CLAIM EXECUTION ---
    print("\n--- Step 4: Execute the approved claim ---")
    if claim_status[4] == 1: # 1 is enum for 'Approved'
        charlie_balance_before = currency_token.balanceOf(charlie)
        insurance_dao.executeClaim(claim_id, {"from": alice})
        charlie_balance_after = currency_token.balanceOf(charlie)
        print("  - Claim executed successfully.")
        print(f"  - Charlie's balance increased by {charlie_balance_after - charlie_balance_before}.")
        print(f"  - New DAO Pool Balance: {currency_token.balanceOf(insurance_dao.address)}")
        print(f"  - Final Claim Status Code: {insurance_dao.claims(claim_id)[4]}")
    else:
        print("  - Claim was not approved, cannot execute.")