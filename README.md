# Rain Protocol: Reputation-Centric Financial System

This project implements the on-chain and off-chain components for a reputation-centric financial system. It aims to create a resilient, decentralized economy where a user's reputation is a tangible, valuable, and dynamic asset.

## Vision

To build a decentralized financial ecosystem where reputation is a core primitive, enabling more equitable access to financial services and fostering trust-based interactions. This system leverages both on-chain smart contracts for execution and off-chain processes for complex computations like reputation scoring.

This implementation focuses on the **smart contract architecture, off-chain support scripts, and local simulation** to demonstrate the viability of the core economic model.

## Core Mechanics

A *promise* is a recorded commitment by one user to another (an amount, an asset, a deadline). Anyone can write a *script*, a contract that records promises and moves value on behalf of users who authorized it. Reputation is what a user earns by keeping promises.

1.  **`CalculusEngine.sol`**: the log of promises and transfers. Scripts are permissionless; a script can only act for users who authorized it, within the allowances they gave it. Every promise pays a fee to the Treasury: a percentage of the amount promised, with a minimum.
2.  **`RainReputation.sol`**: the identity token (non-transferable) and the reputation ledger. A new identity has no reputation. Reputation decays by a fixed fraction each period. It can be bonded: a script holds the bond and either returns it or, on default, destroys it. Beside it each account has a broken-promise counter in the same unit, fading at the same rate. The two are the evidence for a belief about the account: `reliability(user, priorKept, priorBroken)` gives the estimated chance that their next promise is kept, for a reader with that prior.
3.  **Off-chain oracle and `ReputationUpdater.sol`**: the oracle reads the promise log and credits each kept promise with `fee paid / point price` reputation, so reputation has a fixed price and is a record of fees paid on kept promises. A broken promise adds the same weight to its promisor's broken-promise counter; it takes no reputation (the bond does that). Each update is applied at most once.
4.  **`ReputationClaimToken.sol` (RCT)**: a transferable claim on a defaulted promise, minted to the person it was owed to. While someone has claims outstanding against them they are *delinquent*: they cannot borrow or earn reputation.
5.  **`Treasury.sol`**: pays the fees out to reputation holders as a dividend (a Merkle drop). Every fee goes into a payout fund, and each cycle shares out a fixed fraction of it: the reputation decay rate, which the Treasury reads from the reputation contract. In steady state that is what comes in; when fee income changes, dividends follow gradually, at the speed the supply of reputation does.
6.  **`LoanScript.sol`**: a reference script, a fixed-term loan secured by a reputation bond.
7.  **`GuaranteedLoanScript.sol`**: a second reference script, a loan that a guarantor answers for (vouching). It is two promises, borrower to guarantor and guarantor to lender, so a newcomer can borrow on the standing of someone the lender already knows (see `experiments/vouching/`).
8.  **`CurrencyToken.sol` (DMD)**: a mintable ERC-20 standing in for a stablecoin.

Why the rules are what they are (a fixed price per point, decay, fees paid out, no starting reputation) is recorded in `experiments/`, and the reasoning about what reputation should mean in `notes/bayesian-reputation.md`.

## Technology Stack

*   **Smart Contracts:** Solidity `0.8.19`, OpenZeppelin Contracts `4.8.0`
*   **Development Framework:** [Ape](https://docs.apeworx.io/) (`eth-ape` with the `ape-solidity` plugin). Tests and scripts run against Ape's in-process local chain, so no separate node is needed.
*   **Off-Chain Logic:** Python 3.10+ (the `rain` library depends only on `eth-utils`)
*   **Environment:** [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`)

## What's Implemented

### Smart Contracts (`contracts/`)

*   `contracts/token/`: `CurrencyToken.sol`, `RainReputation.sol`, `ReputationClaimToken.sol`
*   `contracts/primitives/`: `CalculusEngine.sol`, `ReputationUpdater.sol`, `Treasury.sol`
*   `contracts/scripts/`: `LoanScript.sol`, `GuaranteedLoanScript.sol`
*   `contracts/test/`: `MockDecaySchedule.sol`, a stand-in used only by the tests

### Off-Chain Python Library (`rain/`)

Installed as a local package. The core logic is pure Python and needs no chain.

*   `reputation.py`: the oracle's rules (promise log to reputation changes).
*   `record.py`: a reader's library. It turns the promise log into one reader's belief about one person, weighing each kept promise by the reader's trust in the counterparty (see `experiments/collusion/`). It also gives the unsecured credit a record supports for a reader who trusts nobody: what the record cost in fees (`graduated_credit`, see `experiments/graduation/`).
*   `dividends.py`, `merkletree.py`: dividend shares and the Merkle drop.
*   `model.py`: a pure-Python model of the protocol's accounting, for simulations (checked against the contracts in `tests/test_model_vs_contracts.py`).
*   `economics.py`: closed forms (what a point is worth, when default pays, the steady state).
*   `belief.py`: reputation as the probability of keeping the next promise; decaying counts against the exact Bayesian filter.
*   `ladder.py`: progressive lending, i.e. how much to lend next given what has been repaid.
*   `provenance.py`, `utils.py`: result stamps and small helpers.

### Experiments (`experiments/`)

Experiments on the protocol's economics, each with predictions written before it was run and the outcome recorded after. Start with `experiments/README.md`.

### Simulation & Management Scripts (`scripts/`)

These Python scripts, run with `ape run <name>`, manage the protocol and simulate user interactions:
1.  **`deploy.py`**: Deploys all smart contracts, links them, mints initial tokens, and saves contract addresses to `deployment_addresses.json`.
2.  **`simulate_loan.py`**: Simulates loan origination, repayment, and default scenarios, showcasing the impact on reputation.
3.  **`run_reputation_oracle.py`**: Simulates the off-chain oracle calculating and submitting reputation updates to `ReputationUpdater.sol`. (This script may use `oracle_state.json` to manage its state).
4.  **`run_dividend_distribution.py`**: Runs a dividend cycle: the fees collected are split pro rata to reputation and claimed through Merkle proofs.
5.  **`run_simulation.py`**: Runs the whole sequence in one session: deploy, loans on a ladder (repaid, reputation earned, a default, its resolution), reputation oracle, dividend distribution. This is the quickest way to see everything work: `uv run ape run run_simulation`.

### Tests (`tests/`)

Run with `uv run ape test`.

*   `tests/unit/`: pure-Python tests of the `rain` library (Merkle tree, dividend shares, fee formula, oracle rules). No contracts involved.
*   `tests/test_*.py`: contract tests, plus `test_loan_script.py` (the full loan lifecycle) and `test_offchain_integration.py` (the `rain` library against the real contracts).
*   `notes/primitives.md` describes the permission model the tests exercise (scripts are permissionless; users grant each script its powers).

## Getting Started

You need [uv](https://docs.astral.sh/uv/). Everything else is installed into a project-local environment.

```bash
uv sync                          # install Ape, the Solidity plugin and the `rain` library
uv run ape compile               # compile the contracts (downloads solc and OpenZeppelin the first time; add --force if a contract edit seems not to take effect)
uv run ape test                  # run all tests
uv run ape test tests/unit       # only the pure-Python tests of the `rain` library
uv run ape run run_simulation    # deploy, loans, oracle, dividends and fee keeper, end to end
```

The individual scripts (`ape run deploy`, `ape run simulate_loan`, ...) each start a fresh in-process chain, so on the default local network only `run_simulation` (which chains them in one session) is useful. To run them one at a time, point Ape at a persistent node with `--network`.

### With Docker

```bash
./docker_helper.sh build      # build the image (compiles the contracts)
./docker_helper.sh test       # run the tests
./docker_helper.sh simulate   # run the full simulation
./docker_helper.sh shell      # open a shell in the container
```

## Future Development Roadmap

This implementation provides a robust foundation. Future development could focus on:

*   **Enhanced Oracle Security and Decentralization:** Improving the trust model for the reputation oracle.
*   **User Interface/Application Layer:** Building a user-facing application (e.g., web or mobile) to interact with the protocol.
*   **Advanced Governance Mechanisms:** Implementing DAO structures for protocol upgrades and parameter changes.
*   **Further Economic Primitives:** Exploring additional financial products or services built upon the reputation and treasury system.
*   **Layer 2 / Mainnet Deployment:** Preparing for and executing deployment on a public testnet and eventually a mainnet or Layer 2 solution.
*   **Formal Audits:** Undergoing security audits of the smart contracts.

## Notes

*   `deployment_addresses.json` (written by `scripts/deploy.py`) stores the addresses of deployed contracts.
*   `oracle_state.json` (written by `scripts/run_reputation_oracle.py`) stores the last block the oracle processed, for a given CalculusEngine deployment.
*   Both are generated files and are not tracked by git.