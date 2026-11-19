# File: scripts/run_simulation.py

# To allow importing the other scripts, make sure the project root is on the Python path.
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts import deploy as deploy_script
from scripts import simulate_loan as simulation_script
from scripts import run_reputation_oracle as oracle_script
from scripts import run_dividend_distribution as dividend_script

def main():
    """
    Runs the entire simulation sequence in a single, controlled session:
    1. Deploys all contracts.
    2. Simulates loans on a ladder: repayment, reputation earned, a default, and its resolution.
    3. Runs the reputation oracle to process the remaining on-chain events.
    4. Runs a dividend cycle (fees -> Merkle drop -> claims).
    """
    print("="*50)
    print("--- STARTING FULL SIMULATION ---")
    print("="*50)

    print("\n\n--- STEP 1: DEPLOYING CONTRACTS ---")
    deploy_script.main()
    print("\n--- DEPLOYMENT COMPLETE ---")

    print("\n\n--- STEP 2: SIMULATING LOAN ACTIONS ---")
    simulation_script.main()
    print("\n--- LOAN SIMULATION COMPLETE ---")

    print("\n\n--- STEP 3: RUNNING REPUTATION ORACLE ---")
    oracle_script.main()
    print("\n--- ORACLE RUN COMPLETE ---")

    print("\n\n--- STEP 4: RUNNING DIVIDEND DISTRIBUTION ---")
    dividend_script.main()
    print("\n--- DIVIDEND DISTRIBUTION COMPLETE ---")

    print("\n\n" + "="*50)
    print("--- FULL SIMULATION FINISHED SUCCESSFULLY ---")
    print("="*50)
