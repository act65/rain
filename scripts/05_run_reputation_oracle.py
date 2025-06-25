import json
from brownie import (
    accounts,
    Contract,
    CalculusEngine,
    # We assume LoanScript and EscrowScript have been updated to use the new engine
    # For this script, we will simulate their new behavior directly
    ReputationUpdater,
    RainReputation,
    web3,
)
from collections import defaultdict
from dataclasses import dataclass, field

# --- Configuration: The Reputation Formula ---
BASE_REP_GAIN_ON_FULFILLMENT = 50 * (10**18) # Base reward for any successful, fee-paid action
SURPLUS_REP_MULTIPLIER = 1.0 # How much to multiply the economic surplus by

# Path to the file where deployment addresses are stored
DEPLOYMENT_ADDRESSES_FILE = "deployment_addresses.json"

@dataclass
class Session:
    """A data class to hold all information about an economic session."""
    action_id: int
    participants: set = field(default_factory=set)
    promises: dict = field(default_factory=dict)
    transfers: list = field(default_factory=list)
    value_deltas: defaultdict = field(default_factory=lambda: defaultdict(int))
    economic_surplus: int = 0

def calculate_reputation_changes(session: Session):
    """
    The core "rules engine". Analyzes a completed session and determines reputation changes.
    This new version includes a base reputation gain for all fulfilled promises.
    """
    increases = []
    decreases = []

    # Rule 1: Calculate Value Deltas and Economic Surplus
    for transfer in session.transfers:
        # Ignore transfers to the treasury for surplus calculation between participants
        if transfer.args['to'] != addresses["treasury_contract"]:
            session.value_deltas[transfer.args['from']] -= transfer.args['amount']
            session.value_deltas[transfer.args['to']] += transfer.args['amount']
    
    session.economic_surplus = sum(session.value_deltas.values())

    # Rule 2: Assign reputation based on promise integrity and surplus
    for promise_id, promise_data in session.promises.items():
        promisor = promise_data.promisor
        
        if promise_data.status == "Fulfilled":
            # REVISED LOGIC: Every fulfilled promise in a fee-paid action gets a base reward.
            rep_gain = BASE_REP_GAIN_ON_FULFILLMENT
            
            # Add reputation proportional to the positive economic surplus created
            if session.economic_surplus > 0:
                # This simple formula gives the surplus reward to the one who received it
                if session.value_deltas[promisor] > 0:
                    rep_gain += int(session.value_deltas[promisor] * SURPLUS_REP_MULTIPLIER)

            increases.append({"user": promisor, "amount": rep_gain, "reason": f"PROMISE_FULFILLED:{promise_id}"})

        elif promise_data.status == "Defaulted":
            rep_loss = 500 * (10**18) # Base penalty
            rep_loss += promise_data.amount # Penalty proportional to promise size
            decreases.append({"user": promisor, "amount": rep_loss, "reason": f"PROMISE_DEFAULTED:{promise_id}"})

    return increases, decreases


def main():
    """Simulates an economic scenario using the new Atomic Action Framework."""
    # --- Setup ---
    owner = accounts[0]
    alice = accounts[1]
    bob = accounts[2]

    global addresses # Make addresses globally accessible for the helper function
    with open(DEPLOYMENT_ADDRESSES_FILE) as f:
        addresses = json.load(f)

    calculus_engine = CalculusEngine.at(addresses["calculus_engine"])
    reputation_updater = ReputationUpdater.at(addresses["reputation_updater"])
    token_contract = Contract.from_explorer(addresses["token_contract"])

    # Grant roles
    updater_role = reputation_updater.UPDATER_ROLE()
    if not reputation_updater.hasRole(updater_role, owner):
        reputation_updater.grantRole(updater_role, owner, {"from": owner})
    
    # We need a mock script contract to act as the session creator
    # In a real test suite, you'd deploy the updated LoanScript.
    # For this script, we'll grant the role to the owner account to simulate.
    session_creator_role = calculus_engine.SESSION_CREATOR_ROLE()
    if not calculus_engine.hasRole(session_creator_role, owner):
        calculus_engine.grantRole(session_creator_role, owner, {"from": owner})

    print("--- Starting Atomic Action Oracle Simulation ---")

    # --- SCENARIO: A Simple Transfer (demonstrates base reputation gain) ---
    print("\n--- Simulating Scenario: Simple Transfer ---")
    transfer_amount = 100 * (10**18)
    
    # User (Alice) must approve the engine for the fee
    fee = calculus_engine.protocolFee()
    token_contract.approve(calculus_engine.address, fee, {"from": alice})

    # 1. The script (owner) initiates the action on behalf of Alice
    action_tx = calculus_engine.monitoredAction(alice.address, {"from": owner})
    action_id = action_tx.events["ActionCreated"]["actionId"]
    print(f"  - Action created with ID: {action_id}. Fee paid by Alice.")

    # 2. The script orchestrates the transfer
    token_contract.approve(calculus_engine.address, transfer_amount, {"from": alice})
    transfer_tx = calculus_engine.monitoredTransfer(action_id, token_contract.address, alice.address, bob.address, transfer_amount, {"from": owner})
    print("  - Monitored transfer complete.")

    # Build the session object for the oracle
    transfer_session = Session(action_id=action_id)
    # In this simple case, there are no promises to fulfill, but the action itself
    # can be seen as an implicit promise that was kept.
    # A more advanced oracle could create a synthetic "promise" for this.
    # For now, we'll skip reputation gain for a transfer to keep the logic focused on explicit promises.
    # The key takeaway is that the fee was paid and the action is logged.
    
    # Let's simulate a loan to show the full flow
    print("\n--- Simulating Scenario: Successful Loan ---")
    principal = 1000 * (10**18)
    repayment = 1100 * (10**18)
    
    # Borrower (Bob) pays the fee
    token_contract.approve(calculus_engine.address, fee, {"from": bob})
    action_tx_loan = calculus_engine.monitoredAction(bob.address, {"from": owner})
    loan_action_id = action_tx_loan.events["ActionCreated"]["actionId"]
    print(f"  - Loan action created with ID: {loan_action_id}.")

    # Create promises
    p1_tx = calculus_engine.monitoredPromise(loan_action_id, alice.address, bob.address, token_contract.address, principal, block.timestamp + 3600, {"from": owner})
    lender_promise_id = p1_tx.events["PromiseCreated"]["promiseId"]
    p2_tx = calculus_engine.monitoredPromise(loan_action_id, bob.address, alice.address, token_contract.address, repayment, block.timestamp + 3600, {"from": owner})
    borrower_promise_id = p2_tx.events["PromiseCreated"]["promiseId"]

    # Fund loan
    token_contract.approve(calculus_engine.address, principal, {"from": alice})
    calculus_engine.monitoredTransfer(loan_action_id, token_contract.address, alice.address, bob.address, principal, {"from": owner})
    calculus_engine.monitoredFulfillment(lender_promise_id, {"from": owner})
    
    # Repay loan
    token_contract.approve(calculus_engine.address, repayment, {"from": bob})
    repay_transfer_tx = calculus_engine.monitoredTransfer(loan_action_id, token_contract.address, bob.address, alice.address, repayment, {"from": owner})
    calculus_engine.monitoredFulfillment(borrower_promise_id, {"from": owner})
    print("  - Loan lifecycle complete.")

    # Build session for the oracle
    loan_session = Session(action_id=loan_action_id)
    loan_session.transfers.append(repay_transfer_tx.events["ValueTransferred"])
    loan_session.promises = {
        lender_promise_id: {"promisor": alice.address, "status": "Fulfilled"},
        borrower_promise_id: {"promisor": bob.address, "status": "Fulfilled"}
    }
    
    # Run the oracle
    increases, decreases = calculate_reputation_changes(loan_session)
    if increases or decreases:
        reputation_updater.applyReputationChanges(increases, decreases, {"from": owner})
        print("  - Oracle has successfully updated on-chain reputation.")

    print("\n--- Atomic Action Oracle Simulation Complete ---")