# Reputation-Centric Economy Demo

This project is a proof-of-concept demonstration of the on-chain mechanics for a reputation-based financial system, as described in the initial vision document.

## Vision

To create a resilient, decentralized, and self-governing digital economy for communities with limited or no internet access. The core principle is to shift security from technical prevention of fraud (which is impossible in an offline environment) to powerful economic incentives, making a user's reputation a tangible, valuable, and forfeitable asset.

This demo focuses exclusively on the **on-chain smart contract architecture** and simulates user interactions via scripts. It intentionally ignores offline functionality, user interfaces, and network latency to prove the viability of the core economic model.

## Technology Stack

*   **Smart Contracts:** Solidity `^0.8.0`
*   **Development Framework:** Python-based Brownie (`v1.19.5+`)
*   **Local Blockchain:** Ganache (`ganache-cli`)
*   **Dependencies:** OpenZeppelin Contracts

## What's Implemented

This demo consists of four core smart contracts and three Python scripts to simulate their interactions.

### Smart Contracts (`contracts/`)

1.  **`CurrencyToken.sol`**: A standard ERC-20 token (`DMD`) that acts as the system's unit of account.
2.  **`ReputationSBT.sol`**: A non-transferable ERC-721 (Soulbound Token) that represents user identity and tracks their reputation score and staked reputation.
3.  **`LoanContract.sol`**: A contract that allows users to request loans by staking their reputation as collateral. It handles the full lifecycle: funding, repayment (which boosts reputation), and default (which slashes reputation).
4.  **`InsuranceDAO.sol`**: A contract demonstrating a more advanced use case. Users can contribute to a collective insurance pool and vote on claims. A member's voting power is weighted by their reputation score from the `ReputationSBT` contract.

### Simulation Scripts (`scripts/`)

1.  **`01_deploy.py`**: Deploys all contracts, links them together, mints initial currency and reputation tokens for test users (Alice, Bob, Charlie), and saves the contract addresses to a file.
2.  **`02_simulate_loan.py`**: Runs two scenarios against the `LoanContract`:
    *   **Happy Path:** Alice successfully borrows from and repays Bob, resulting in a reputation increase.
    *   **Unhappy Path:** Charlie defaults on a loan from Bob, resulting in his reputation being slashed.
3.  **`03_simulate_insurance.py`**: Simulates the `InsuranceDAO`, where members vote on a claim. It demonstrates how Alice's higher reputation gives her vote more weight than Bob's, allowing a claim to be approved.

## Getting Started

### Prerequisites

*   Python 3.8+
*   Node.js and npm (for Ganache)
*   `ganache-cli` installed globally (`npm install -g ganache-cli`)
*   `eth-brownie` installed (`pip install eth-brownie`)
    *   Docker (optional, for containerized setup)

### Installation & Running the Demo

1.  **Clone the Repository**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Install Dependencies**
    Brownie will automatically install the OpenZeppelin dependency specified in `brownie-config.yaml` the first time you compile or run a script.

3.  **Start the Local Blockchain (Terminal 1)**
    Open a terminal and run Ganache with a deterministic mnemonic. **Leave this terminal running.**
    ```bash
    ganache-cli \
        --mnemonic "your test mnemonic here" \
        --port 8545 \
        --accounts 10 \
        --defaultBalanceEther 1000 \
        --gasLimit 12000000 \
        --deterministic
    ```

4.  **Run the Scripts (Terminal 2)**
    Open a second terminal in the same project directory. Run the scripts in the following order:

    *   **First, deploy the contracts:**
        ```bash
        brownie run scripts/01_deploy.py --network development
        ```
        This will compile everything and create a `deployment_addresses.json` file.

    *   **Next, simulate the loan contract:**
        ```bash
        brownie run scripts/02_simulate_loan.py --network development
        ```

    *   **Finally, simulate the insurance DAO:**
        ```bash
        brownie run scripts/03_simulate_insurance.py --network development
        ```

## Running with Docker (Recommended for Consistency)

This project includes a Docker setup to provide a consistent environment for development and testing.

### Prerequisites for Docker

*   Docker installed and running on your system.

### Building the Docker Image

First, build the Docker image. From the project root directory:
```bash
./docker_helper.sh build
```

### Running Tests with Docker

The easiest way to run the tests using Docker is with the `all` command, which handles starting Ganache, running tests, and stopping Ganache:
```bash
./docker_helper.sh all
```
This will:
1. Build the image if it hasn't been built (or use the existing one).
2. Start a Ganache container in the background.
3. Execute `brownie test` inside the container.
4. Stop and remove the Ganache container.

Alternatively, you can manage the Ganache container and test execution separately:

1.  **Start Ganache Container:**
    ```bash
    ./docker_helper.sh start_ganache
    ```
    This will start a Ganache instance in a detached container, exposing port 8545.

2.  **Run Brownie Tests:**
    Once Ganache is running, execute the tests:
    ```bash
    ./docker_helper.sh test
    ```
    This command runs `brownie test` inside the already running container.

3.  **Stop Ganache Container:**
    When you're done, stop the Ganache container:
    ```bash
    ./docker_helper.sh stop_ganache
    ```

### Interactive Shell in Docker Container

To get an interactive shell inside the running container (e.g., for manual `brownie console` sessions or debugging):
1. Ensure the Ganache container is running: `./docker_helper.sh start_ganache`
2. Open a shell:
   ```bash
   ./docker_helper.sh shell
   ```
   You'll be inside the container as the `appuser` in the `/home/appuser/app` directory. Brownie and Ganache CLI commands will be available.

## Future Development Roadmap

This demo provides the foundation for the on-chain logic. A full implementation would require building out the other layers of the system:

*   **Layer 3: The Application Layer:** An offline-first mobile application with QR code transactions and "sneakernet" syncing capabilities.
*   **Layer 0: Enhanced Identity:** A "Web of Trust" onboarding system where new users must be vouched for by existing members.
*   **Layer 2: Advanced Economic Mechanisms:**
    *   A **Treasury & Dividend Contract** that earns yield on system capital and distributes it to users as a "Reputation Dividend," making reputation a yield-bearing asset.
    *   More complex governance and dispute resolution mechanisms.
*   **Layer 1: Mainnet Readiness:** Migrating from a local Ganache instance to a public testnet and eventually a mainnet L2 solution (like Arbitrum or Polygon) using a real stablecoin.