from brownie import (
    accounts,
    chain,
    LoanScript,
    CalculusEngine,
    CurrencyToken,
    RainReputation,
    ReputationClaimToken,
)
from rain.utils import load_deployment_data
import time

DEPLOYMENT_FILE = "deployment_addresses.json"

def main():
    """
    Simulates the full loan cycle:
    1. Happy Path: A successful loan request, funding, and repayment.
    2. Unhappy Path: A loan default, resulting in an RCT mint.
    3. Resolution Path: The settlement of the debt, burning of the RCT, and release of the stake.
    """
    print("--- LOAN SIMULATION (FULL LIFECYCLE) ---")

    # --- 1. SETUP ---
    print("\n--- Phase 1: Setup ---")
    # Load accounts
    deployer = accounts[0]
    alice = accounts[1] # Lender
    bob = accounts[2]   # Borrower (Happy Path)
    charlie = accounts[3] # Borrower (Unhappy & Resolution Path)

    # Load contract addresses
    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        print("Failed to load deployment addresses. Exiting.")
        return

    print("\n--- Phase 1: Setup ---")
    # Create contract objects
    calculus_engine = CalculusEngine.at(addresses["CalculusEngine"])
    currency_token = CurrencyToken.at(addresses["CurrencyToken"])
    rain_reputation = RainReputation.at(addresses["RainReputation"])
    rct_contract = ReputationClaimToken.at(addresses["ReputationClaimToken"])

    # Deploy the LoanScript application
    print("Deploying the LoanScript application...")
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
    print("Granted MINTER_ROLE to LoanScript.")

    # Grant the LoanScript permission to create sessions in the CalculusEngine
    print("Granting SESSION_CREATOR_ROLE to LoanScript...")
    session_creator_role = calculus_engine.SESSION_CREATOR_ROLE()
    calculus_engine.grantRole(session_creator_role, loan_script.address, {"from": deployer})
    print("Granted SESSION_CREATOR_ROLE to LoanScript.")

    # --- 2. HAPPY PATH SIMULATION: Bob borrows from Alice ---
    print("\n\n--- Phase 2: Happy Path (Bob borrows from Alice) ---")
    principal = 1000 * (10**18)
    interest = 50 * (10**18)
    duration_seconds = 60 * 60 * 24 * 30 # 30 days
    reputation_stake = 50 * (10**18)

    print(f"Initial Reputation - Bob: {rain_reputation.reputationScores(bob) / 10**18}")
    print(f"Initial Balance - Alice: {currency_token.balanceOf(alice) / 10**18}, Bob: {currency_token.balanceOf(bob) / 10**18}")

    print("\nStep A-pre: Bob approves the protocol fee...")
    protocol_fee = calculus_engine.protocolFee()
    currency_token.approve(calculus_engine.address, protocol_fee, {"from": bob})
    print(f"  - Bob approved CalculusEngine to spend {protocol_fee / 10**18} for the protocol fee.")

    print("\nStep A: Bob requests a loan...")
    tx_req = loan_script.requestLoan(alice.address, principal, interest, duration_seconds, reputation_stake, {"from": bob})
    loan_id = tx_req.events["LoanRequested"]["loanId"]
    print(f"  - Loan {loan_id} requested. Bob's Staked Reputation: {rain_reputation.stakedReputation(bob) / 10**18}")

    print("\nStep B: Alice funds the loan...")
    currency_token.approve(calculus_engine.address, principal, {"from": alice})
    loan_script.fundLoan(loan_id, {"from": alice})
    print(f"  - Loan funded. Balances: Alice={currency_token.balanceOf(alice) / 10**18}, Bob={currency_token.balanceOf(bob) / 10**18}")

    print("\nStep C: Bob repays the loan...")
    repayment_amount = principal + interest
    currency_token.approve(calculus_engine.address, repayment_amount, {"from": bob})
    loan_script.repayLoan(loan_id, {"from": bob})
    print("  - Loan repaid.")

    print("\nHappy Path Final State:")
    print(f"  - Bob's Staked Reputation: {rain_reputation.stakedReputation(bob) / 10**18} (should be 0)")
    print(f"  - Final Balances: Alice={currency_token.balanceOf(alice) / 10**18}, Bob={currency_token.balanceOf(bob) / 10**18}")

    # --- 3. UNHAPPY PATH SIMULATION: Charlie borrows from Alice and defaults ---
    print("\n\n--- Phase 3: Unhappy Path (Charlie borrows from Alice) ---")
    print(f"Initial Reputation - Charlie: {rain_reputation.reputationScores(charlie) / 10**18}")

    print("\nStep A-pre: Charlie approves the protocol fee...")
    # We can re-use the protocol_fee variable from above
    currency_token.approve(calculus_engine.address, protocol_fee, {"from": charlie})
    print(f"  - Charlie approved CalculusEngine to spend {protocol_fee / 10**18} for the protocol fee.")

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
    print(f"  - Charlie's Delinquent Status: {rain_reputation.isDelinquent(charlie)}")
    assert rct_contract.ownerOf(rct_id) == alice.address
    assert rain_reputation.isDelinquent(charlie) == True


    # --- 4. DEBT RESOLUTION PATH: Charlie settles his debt ---
    print("\n\n--- Phase 4: Debt Resolution Path (Charlie settles with Alice) ---")
    print("This simulates an off-chain settlement where Charlie pays Alice, and she gives him the RCT.")

    print(f"\nStep A: Alice transfers the RCT to Charlie...")
    rct_contract.transferFrom(alice.address, charlie.address, rct_id, {"from": alice})
    print(f"  - RCT {rct_id} is now owned by Charlie.")
    assert rct_contract.ownerOf(rct_id) == charlie.address

    print("\nStep B-pre: Charlie approves the LoanScript to burn the RCT...")
    rct_contract.approve(loan_script.address, rct_id, {"from": charlie})
    print(f"  - Charlie approved LoanScript to manage RCT {rct_id}.")

    print("\nStep B: Charlie resolves the default using the LoanScript...")
    # This assumes your LoanScript has the new `resolveDefault` function.
    loan_script.resolveDefault(rct_id, {"from": charlie})
    print("  - `resolveDefault` called successfully.")

    print("\nResolution Path Final State:")
    print(f"  - Charlie's Staked Reputation: {rain_reputation.stakedReputation(charlie) / 10**18} (should be 0)")
    print(f"  - Charlie's Delinquent Status: {rain_reputation.isDelinquent(charlie)} (should be False)")
    
    # Verify the RCT was burned
    try:
        rct_contract.ownerOf(rct_id)
        # If this line is reached, the test fails because the token still exists.
        assert False, "RCT was not burned!"
    except Exception as e:
        # We expect an exception because the token is burned.
        print(f"  - VERIFIED: RCT {rct_id} has been burned.")

    assert rain_reputation.stakedReputation(charlie) == 0
    assert rain_reputation.isDelinquent(charlie) == False
    print("  - VERIFIED: Charlie's stake was released and his delinquent status was cleared.")

    print("\n\n--- SIMULATION COMPLETE ---")