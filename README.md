# Rain Protocol: Reputation-Centric Financial System

This project implements the on-chain and off-chain components for a reputation-centric financial system. It aims to create a resilient, decentralized economy where a user's reputation is a tangible, valuable, and dynamic asset.

## Vision

To build a decentralized financial ecosystem where reputation is a core primitive, enabling more equitable access to financial services and fostering trust-based interactions. This system leverages both on-chain smart contracts for execution and off-chain processes for complex computations like reputation scoring.

This implementation focuses on the **smart contract architecture, off-chain support scripts, and local simulation** to demonstrate the viability of the core economic model.

## Core Mechanics

The Rain Protocol revolves around several key components:

1.  **`CurrencyToken.sol` (DMD):** A standard ERC-20 token that serves as the system's primary unit of account and transactional currency.
2.  **`RainReputation.sol`:** A specialized token contract (e.g., ERC721 or custom) representing a user's reputation. This reputation is dynamic and influenced by user behavior within the protocol.
3.  **`ReputationClaimToken.sol`:** A token that may be used to claim rewards or benefits based on a user's reputation score.
4.  **`ReputationUpdater.sol`:** A smart contract responsible for updating user reputation scores on-chain. It is designed to be called by a trusted oracle.
5.  **`CalculusEngine.sol`:** A contract that handles complex calculations required by the protocol, potentially related to risk assessment, reward distribution, or other financial mechanics.
6.  **`Treasury.sol`:** Manages protocol funds, collects fees generated from activities (e.g., loan origination, repayments), and facilitates dividend distribution to reputation holders.
7.  **Loan System (via `LoanScript.sol` and off-chain logic):** Users can request and receive loans, with terms and conditions potentially influenced by their reputation. Repayment and defaults directly impact reputation scores. `LoanScript.sol` likely provides on-chain functions for loan lifecycle management.
8.  **Off-Chain Reputation Oracle:** User reputation is calculated off-chain based on various factors and submitted to the `ReputationUpdater` contract by a designated oracle script (`scripts/run_reputation_oracle.py`). This allows for more complex and nuanced reputation scoring than feasible purely on-chain.
9.  **Dividend Distribution:** The protocol features a mechanism to distribute dividends to `RainReputation` token holders, managed by the `Treasury` and triggered by `scripts/run_dividend_distribution.py`.
10. **Protocol Fees:** The system incorporates configurable protocol fees, managed via `scripts/run_set_protocol_fee.py`.
11. **`rain-offchain` Python Library:** A local Python library (`rain/`) containing modules for off-chain tasks such as reputation calculation, dividend processing, Merkle tree generation (`rain/merkletree.py`), and interacting with the smart contracts.

## Technology Stack

*   **Smart Contracts:** Solidity `^0.8.19`
*   **Development Framework:** Python-based Brownie (`v1.19.0+`)
*   **Local Blockchain:** Ganache (`ganache-cli`)
*   **Dependencies:**
    *   OpenZeppelin Contracts `@4.8.0`
    *   `pymerkle` (for Merkle tree generation in the off-chain library)
*   **Off-Chain Logic:** Python 3.9+
*   **Node.js:** `18.x` (for `ganache-cli`)

## What's Implemented

### Smart Contracts (`contracts/`)

The contracts are organized into logical groups:
*   `contracts/token/`: `CurrencyToken.sol`, `RainReputation.sol`, `ReputationClaimToken.sol`
*   `contracts/primitives/`: `CalculusEngine.sol`, `ReputationUpdater.sol`, `Treasury.sol`
*   `contracts/scripts/`: `LoanScript.sol` (utility/interaction script contract)
*   `contracts/mocks/`: Mock contracts for testing.

Key contracts include:
1.  **`CurrencyToken.sol`**: ERC-20 token (DMD) for transactions.
2.  **`RainReputation.sol`**: Represents user reputation.
3.  **`ReputationClaimToken.sol`**: For claiming reputation-based benefits.
4.  **`CalculusEngine.sol`**: Handles core protocol calculations.
5.  **`ReputationUpdater.sol`**: Updates on-chain reputation scores via an oracle.
6.  **`Treasury.sol`**: Manages protocol funds, fees, and dividend distributions.
7.  **`LoanScript.sol`**: Facilitates on-chain loan operations.

### Off-Chain Python Library (`rain/`)

Located in the `rain` directory and installed as a local package, this library includes:
*   `reputation.py`: Logic for calculating reputation scores.
*   `dividends.py`: Logic for processing dividend distributions.
*   `merkletree.py`: Utilities for creating and verifying Merkle trees.
*   `protocol_fee.py`: Logic for managing protocol fees.
*   `utils.py`: Shared utility functions.

### Simulation & Management Scripts (`scripts/`)

These Python scripts, run with Brownie, manage the protocol and simulate user interactions:
1.  **`deploy.py`**: Deploys all smart contracts, links them, mints initial tokens, and saves contract addresses to `deployment_addresses.json`.
2.  **`simulate_loan.py`**: Simulates loan origination, repayment, and default scenarios, showcasing the impact on reputation.
3.  **`run_reputation_oracle.py`**: Simulates the off-chain oracle calculating and submitting reputation updates to `ReputationUpdater.sol`. (This script may use `oracle_state.json` to manage its state).
4.  **`run_dividend_distribution.py`**: Simulates the process of distributing dividends from the `Treasury` to reputation holders.
5.  **`run_set_protocol_fee.py`**: Demonstrates how protocol fees can be configured.
6.  **`run_simulation.py`**: A general script that may run a comprehensive simulation of various protocol features.

## Getting Started

### Prerequisites

*   Python 3.9+
*   Node.js 18.x and npm (for `ganache-cli`)
*   `ganache-cli` installed globally: `npm install -g ganache-cli`
*   `eth-brownie` installed: `pip install eth-brownie>=1.19.0,<2.0.0`
*   Docker (Recommended for the most consistent setup)

### Installation & Running (Non-Docker - for understanding, Docker recommended)

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url> # Replace <your-repo-url> with the actual URL
    cd <your-repo-name> # Replace <your-repo-name> with the directory name
    ```

2.  **Install Python Dependencies:**
    This includes Brownie and dependencies for the `rain-offchain` library.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install `rain-offchain` Library:**
    Install the local Python package.
    ```bash
    pip install .
    ```
    (For development, you might prefer `pip install -e .`)

4.  **Start the Local Blockchain (Terminal 1):**
    Open a terminal and run Ganache with the project's deterministic mnemonic. **Leave this terminal running.**
    ```bash
    ganache-cli \
        --mnemonic "candy maple cake sugar pudding cream honey rich smooth crumble sweet treat" \
        --port 8545 \
        --accounts 10 \
        --defaultBalanceEther 1000 \
        --gasLimit 12000000 \
        --deterministic \
        --host 127.0.0.1
    ```

5.  **Run the Scripts (Terminal 2):**
    Open a second terminal in the project directory. Run scripts using Brownie:

    *   **Deploy contracts:**
        ```bash
        brownie run scripts/deploy.py --network development
        ```
        This creates/updates `deployment_addresses.json`.

    *   **Run simulations/operations (examples):**
        ```bash
        brownie run scripts/simulate_loan.py --network development
        brownie run scripts/run_reputation_oracle.py --network development
        # ... and other scripts as needed
        ```

## Running with Docker (Recommended for Consistency)

This project includes a comprehensive Docker setup for a consistent development and testing environment. The `docker_helper.sh` script simplifies Docker usage.

### Prerequisites for Docker

*   Docker installed and running on your system.

### Building the Docker Image

The Docker image includes all necessary system dependencies, Python packages, global `ganache-cli`, pre-compiles the smart contracts, and installs the local `rain-offchain` library.
Build the image once (or when Dockerfile/dependencies change):
```bash
./docker_helper.sh build
```

### Running All Tests with Docker (Easiest Method)

The `all` command handles starting Ganache, running Brownie tests, and stopping Ganache:
```bash
./docker_helper.sh all
```
This will:
1. Build the image if it's not already built.
2. Start a Ganache container in the background using the project's standard mnemonic.
3. Execute `brownie test -s` inside the container.
4. Stop and remove the Ganache container.

### Managing Ganache and Tests Separately with Docker

1.  **Start Ganache Container:**
    ```bash
    ./docker_helper.sh start_ganache
    ```
    This starts Ganache in a detached container, exposing port 8545. It uses the mnemonic: `"candy maple cake sugar pudding cream honey rich smooth crumble sweet treat"`. The container is named `solidity_app_dev`.

2.  **Run Brownie Tests (or other scripts):**
    Once Ganache is running, execute tests or any Brownie script by `exec`-ing into the container:
    ```bash
    ./docker_helper.sh test
    ```
    To run a specific script (e.g., deploy):
    ```bash
    docker exec solidity_app_dev brownie run scripts/deploy.py --network development
    ```

3.  **Stop Ganache Container:**
    When done, stop the Ganache container:
    ```bash
    ./docker_helper.sh stop_ganache
    ```

### Interactive Shell in Docker Container

To get an interactive bash shell inside the running application container:
1. Ensure the Ganache container is running: `./docker_helper.sh start_ganache`
2. Open a shell:
   ```bash
   ./docker_helper.sh shell
   ```
   You'll be inside the container as `appuser` in `/home/appuser/app`. All project tools and scripts are available.

## Future Development Roadmap

This implementation provides a robust foundation. Future development could focus on:

*   **Enhanced Oracle Security and Decentralization:** Improving the trust model for the reputation oracle.
*   **User Interface/Application Layer:** Building a user-facing application (e.g., web or mobile) to interact with the protocol.
*   **Advanced Governance Mechanisms:** Implementing DAO structures for protocol upgrades and parameter changes.
*   **Further Economic Primitives:** Exploring additional financial products or services built upon the reputation and treasury system.
*   **Layer 2 / Mainnet Deployment:** Preparing for and executing deployment on a public testnet and eventually a mainnet or Layer 2 solution.
*   **Formal Audits:** Undergoing security audits of the smart contracts.

## Notes

*   The `deployment_addresses.json` file stores the addresses of deployed contracts.
*   The `oracle_state.json` file is likely used by `scripts/run_reputation_oracle.py` to persist or load oracle-related data.