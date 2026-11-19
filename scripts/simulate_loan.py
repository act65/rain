# File: scripts/simulate_loan.py

from ape import accounts, chain, project

from rain.utils import expect_revert, load_deployment_data
from scripts import run_reputation_oracle as oracle_script

DEPLOYMENT_FILE = "deployment_addresses.json"


def main():
    """
    Simulates the loan lifecycle on a ladder, starting from identities with no reputation:
    1. First rung: Bob and Charlie each take a small loan with no bond, and repay it.
       The oracle then credits the reputation they earned (in proportion to the fee paid).
    2. Second rung: Charlie bonds some of that reputation against a larger loan and defaults.
       The bond is destroyed and Alice receives a claim (RCT).
    3. Resolution: Charlie settles, burns the RCT, and is no longer delinquent.
    """
    print("--- LOAN SIMULATION (FULL LIFECYCLE) ---")

    # --- 1. SETUP ---
    print("\n--- Phase 1: Setup ---")
    deployer = accounts.test_accounts[0]
    alice = accounts.test_accounts[1] # Lender
    bob = accounts.test_accounts[2]   # Borrower who repays
    charlie = accounts.test_accounts[3] # Borrower who later defaults

    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        raise RuntimeError("Could not load deployment addresses. Run scripts/deploy.py first.")

    calculus_engine = project.CalculusEngine.at(addresses["CalculusEngine"])
    currency_token = project.CurrencyToken.at(addresses["CurrencyToken"])
    rain_reputation = project.RainReputation.at(addresses["RainReputation"])
    rct_contract = project.ReputationClaimToken.at(addresses["ReputationClaimToken"])

    print("Deploying the LoanScript application...")
    loan_script = project.LoanScript.deploy(
        calculus_engine.address,
        rain_reputation.address,
        rct_contract.address,
        currency_token.address,
        sender=deployer,
    )
    print(f"LoanScript deployed at: {loan_script.address}")

    # Scripts need no role from the protocol. Instead, each user grants this script
    # exactly the powers it needs over them.
    max_uint = 2**256 - 1
    e18 = 10**18
    duration_seconds = 60 * 60 * 24 * 20 # 20 days
    first_principal, first_interest = 100 * e18, 5 * e18
    second_principal, second_interest = 110 * e18, 5 * e18
    reputation_stake = 20 * e18

    print("\nUsers grant the LoanScript its permissions...")
    for user in (alice, bob, charlie):
        # The engine is the contract that actually moves tokens
        currency_token.approve(calculus_engine.address, max_uint, sender=user)
    # Alice lends: the script may move the principals she is prepared to lend
    calculus_engine.approveScript(loan_script.address, currency_token.address, 1000 * e18, sender=alice)
    for borrower in (bob, charlie):
        # The script may make promises in the borrower's name...
        calculus_engine.setScriptAuthorization(loan_script.address, True, sender=borrower)
        # ...move the protocol fees and the repayments...
        calculus_engine.approveScript(loan_script.address, currency_token.address, 1000 * e18, sender=borrower)
        # ...and bond (and, on default, destroy) this much of their reputation.
        rain_reputation.approveStake(loan_script.address, reputation_stake, sender=borrower)

    # --- 2. FIRST RUNG: small unbonded loans, repaid ---
    print("\n\n--- Phase 2: First rung (no reputation yet, so no bond) ---")
    for name, borrower in (("Bob", bob), ("Charlie", charlie)):
        balance = currency_token.balanceOf(borrower)
        loan_script.requestLoan(alice.address, first_principal, first_interest, duration_seconds, 0, sender=borrower)
        loan_id = loan_script.loanCount()
        loan_script.fundLoan(loan_id, sender=alice)  # the promise is recorded and the borrower pays the fee
        loan_script.repayLoan(loan_id, sender=borrower)
        fee = calculus_engine.promises(loan_script.loans(loan_id).promiseId).feePaid
        print(f"  - {name} borrowed {first_principal / e18} DMD and repaid it. Fee paid: {fee / e18} DMD; "
              f"total cost {(balance - currency_token.balanceOf(borrower)) / e18} DMD.")
        assert rain_reputation.reputationScores(borrower) == 0  # until the oracle runs

    print("\nThe oracle processes the promise log...")
    oracle_script.main()
    for name, borrower in (("Bob", bob), ("Charlie", charlie)):
        print(f"  - {name}'s reputation: {rain_reputation.reputationScores(borrower) / e18}")
    earned = rain_reputation.reputationScores(charlie)
    assert earned > reputation_stake

    # --- 3. SECOND RUNG: Charlie bonds reputation, borrows more, and defaults ---
    print("\n\n--- Phase 3: Second rung (Charlie bonds reputation, then defaults) ---")
    loan_script.requestLoan(alice.address, second_principal, second_interest, duration_seconds, reputation_stake, sender=charlie)
    default_loan_id = loan_script.loanCount()
    print(f"  - Loan {default_loan_id} requested. Charlie's staked reputation: {rain_reputation.stakedReputation(charlie) / e18}")
    loan_script.fundLoan(default_loan_id, sender=alice)
    print("  - Loan funded.")

    print("\nSimulating time passing beyond the deadline...")
    chain.pending_timestamp += duration_seconds + 1
    chain.mine()

    print("\nAlice claims the default...")
    loan_script.claimDefault(default_loan_id, sender=alice)
    rct_id = rct_contract.claimForPromise(loan_script.loans(default_loan_id).promiseId)
    print(f"  - Default claimed. RCT with ID {rct_id} was minted to Alice for {rct_contract.claims(rct_id).shortfallAmount / e18} DMD.")
    print(f"  - Charlie's Delinquent Status: {rain_reputation.isDelinquent(charlie)}")
    print(f"  - Charlie's Reputation: {rain_reputation.reputationScores(charlie) / e18} (his bond was forfeited)")
    assert rct_contract.ownerOf(rct_id) == alice.address
    assert rain_reputation.isDelinquent(charlie) == True
    assert rain_reputation.reputationScores(charlie) == earned - reputation_stake
    assert rain_reputation.stakedReputation(charlie) == 0

    # --- 4. DEBT RESOLUTION PATH: Charlie settles his debt ---
    print("\n\n--- Phase 4: Debt Resolution Path (Charlie settles with Alice) ---")
    print("This simulates an off-chain settlement where Charlie pays Alice, and she gives him the RCT.")
    rct_contract.transferFrom(alice.address, charlie.address, rct_id, sender=alice)
    assert rct_contract.ownerOf(rct_id) == charlie.address
    rct_contract.approve(loan_script.address, rct_id, sender=charlie)
    loan_script.resolveDefault(rct_id, sender=charlie)

    print("\nResolution Path Final State:")
    print(f"  - Charlie's Delinquent Status: {rain_reputation.isDelinquent(charlie)} (should be False)")
    print(f"  - Charlie's Reputation: {rain_reputation.reputationScores(charlie) / e18} (the forfeited bond is not returned)")

    expect_revert(lambda: rct_contract.ownerOf(rct_id), "invalid token ID")
    print(f"  - VERIFIED: RCT {rct_id} has been burned.")
    assert rain_reputation.isDelinquent(charlie) == False
    assert rain_reputation.reputationScores(charlie) == earned - reputation_stake
    print("  - VERIFIED: Charlie's delinquent status was cleared.")

    print("\n\n--- SIMULATION COMPLETE ---")
