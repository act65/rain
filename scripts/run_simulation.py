# File: scripts/run_full_simulation.py

# To allow importing from other scripts in the same directory,
# we might need to adjust the Python path. Brownie often handles this,
# but this is a robust way to ensure it works.
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the main functions from your existing scripts
from scripts import deploy as deploy_script
from scripts import simulate_loan as simulation_script
from scripts import run_reputation_oracle as oracle_script

def main():
    """
    Runs the entire simulation sequence in a single, controlled session:
    1. Deploys all contracts.
    2. Simulates loan creation, fulfillment, and default.
    3. Runs the reputation oracle to process the on-chain events.
    """
    print("="*50)
    print("--- STARTING FULL SIMULATION ---")
    print("="*50)

    # --- STEP 1: DEPLOY CONTRACTS ---
    print("\n\n--- STEP 1: DEPLOYING CONTRACTS ---")
    deploy_script.main()
    print("\n--- DEPLOYMENT COMPLETE ---")

    # --- STEP 2: SIMULATE LOAN LIFECYCLES ---
    print("\n\n--- STEP 2: SIMULATING LOAN ACTIONS ---")
    simulation_script.main()
    print("\n--- LOAN SIMULATION COMPLETE ---")

    # --- STEP 3: RUN THE REPUTATION ORACLE ---
    print("\n\n--- STEP 3: RUNNING REPUTATION ORACLE ---")
    oracle_script.main()
    print("\n--- ORACLE RUN COMPLETE ---")

    print("\n\n" + "="*50)
    print("--- FULL SIMULATION FINISHED SUCCESSFULLY ---")
    print("="*50)