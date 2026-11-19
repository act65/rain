### **The Atomic Primitives: A Guide to the Rain eDSL**

#### **1. A New Paradigm: The Embedded Domain-Specific Language (eDSL)**

To build on Rain, it's important to understand that you are not just interacting with a set of contracts; you are using an **Embedded Domain-Specific Language (eDSL)** designed for one specific purpose: **the creation of verifiable economic agreements.**

Instead of a single, monolithic contract that tries to do everything, the protocol provides a small, powerful set of "words"—or **atomic primitives**. Your smart contract ("script") combines these words to write "sentences" that describe a financial agreement.

This approach has enormous benefits:
*   **Security:** The primitives are simple, heavily audited, and constrained. The security of the entire system relies on these few building blocks, not on the complex logic of every application built on top.
*   **Expressiveness:** The language is designed to make your economic *intent* clear. This makes your code easier to write, audit, and trust.
*   **Flexibility:** Like LEGO bricks, these simple primitives can be composed in near-infinite ways to build applications far beyond what the original protocol designers envisioned.

#### **2. The Rain eDSL: A Language of Promises**

Different protocols have their own eDSLs, tailored to their domain:
*   **Aave's** eDSL is about **money** (`deposit`, `borrow`, `liquidate`).
*   **OpenZeppelin Governor's** eDSL is about **power** (`propose`, `castVote`, `execute`).
*   **Yearn's** eDSL is about **yield** (`deposit`, `withdraw`).

The Rain eDSL is more foundational. It is a language for **promises**.

You use the Rain eDSL to describe commitments between parties (`monitoredPromise`), the conditions for their resolution (`monitoredFulfillment`, `monitoredDefault`), the value that changes hands (`monitoredTransfer`), and the collateral that backs them (`stake`). Because promises are the bedrock of all economic activity, the Rain eDSL provides a universal framework for building almost any financial application.

#### **3. The `CalculusEngine`: An Economic State Machine Interpreter**

A language needs an interpreter. The `CalculusEngine.sol` contract is that interpreter. It is an **Economic State Machine Interpreter**.

*   **Your Script is the "Source Code":** The sequence of calls your `LoanScript.sol` makes to the `CalculusEngine` and `RainReputation` contracts is a "program" written in the Rain eDSL.
*   **The `CalculusEngine` is the "Interpreter":** It receives your high-level instructions (e.g., `monitoredPromise`) and executes them, performing the necessary low-level state changes within the EVM. It validates the "grammar" of your program, ensuring that every promise is part of a fee-paid action.

This interpreter model is what guarantees the security and integrity of the ecosystem. A bug in your script cannot corrupt the interpreter.

#### **4. The Primitives Toolkit**

##### **`CalculusEngine` Primitives (The Interpreter's Instruction Set)**

*   `monitoredAction(user)`
    *   **Purpose:** The mandatory entry point for any economic session.
    *   **Function:** Creates a unique `actionId` that only the calling script can add to. Free. The `user` must have authorized the script.

*   `monitoredPromise(actionId, ...)`
    *   **Purpose:** To create a verifiable, future obligation.
    *   **Function:** Logs a promise, links it to the `actionId`, and charges the fee to the promisor: a percentage of the amount promised, with a minimum. The fee paid is recorded with the promise, and a kept promise earns reputation in proportion to it (`fee / pointPrice`). The promisor must have authorized the script, and cannot be the promisee.

*   `monitoredTransfer(actionId, ...)` & `monitoredNftTransfer(actionId, ...)`
    *   **Purpose:** To execute a value transfer of a fungible (ERC20) or non-fungible (ERC721) token.
    *   **Function:** Securely moves assets, logging the transfer as part of the `actionId`'s session.

*   `monitoredFulfillment(promiseId)` & `monitoredDefault(promiseId)`
    *   **Purpose:** To resolve a promise.
    *   **Function:** Changes a promise's status, creating the event the off-chain oracle uses to assign reputation.

##### **`RainReputation` Primitives (The Collateral Vault)**

*   `stake(user, amount, purposeId)`
    *   **Purpose:** To lock reputation as a bond.
    *   **Function:** Marks a portion of a user's reputation as "staked" under `purposeId`. A bond decays at the same rate as the score it is part of. The caller becomes the stake's **controller**. A script can only stake what the user allowed it to with `approveStake`.

*   `releaseStake(purposeId)`
    *   **Purpose:** To return the bond once an obligation is met.
    *   **Function:** Releases the stake. Only its controller can call this (so a borrower cannot unlock their own bond).

*   `forfeitStake(purposeId)`
    *   **Purpose:** To make a broken promise cost something that scales with what was at stake.
    *   **Function:** Destroys the staked reputation. Only the stake's controller can call this.

##### **Permissions: scripts are permissionless, users are not powerless**

Anyone can deploy a script; no protocol role is involved. A script has exactly the powers each user grants *that script*:

*   `CalculusEngine.setScriptAuthorization(script, bool)`: the script may open actions and make promises in your name.
*   `CalculusEngine.approveScript(script, asset, amount)`: the script may move this much of your tokens (including the protocol fees you owe). An allowance given to one script is useless to another.
*   `CalculusEngine.setScriptNftApproval(script, asset, bool)`: the script may move your NFTs of a collection.
*   `RainReputation.approveStake(script, amount)`: the script may bond (and on default destroy) this much of your reputation.

The `ReputationClaimToken` needs no minter role either: an RCT can only be minted for a promise the engine records as `Defaulted`, by that promise's script, once, with terms copied from the log.

#### **5. Economic Completeness & Future Extensibility**

The current set of primitives is designed to be **economically complete**, meaning it is sufficient to construct a vast range of complex financial applications.

However, this is a living language. The framework is designed to be extensible through governance. While you can build an escrow contract today by having your script hold the funds, a future version of the `CalculusEngine` could introduce new, more efficient primitives to make this even easier.

**Potential Future Primitives (A Problem for Later):**
*   **`conditionalTransfer`:** A primitive that holds funds within the `CalculusEngine` itself and releases them only when a specific promise is fulfilled.
*   **`conditionalPromise`:** A promise that is only activated if another promise is fulfilled or defaulted, allowing for complex, chained agreements.

The decision to add new primitives will be up to the Rain DAO, allowing the eDSL to evolve with the needs of the developers building on it. For now, the existing toolkit provides a powerful and complete foundation for the next generation of decentralized finance.

<!-- make a note about how control flow is avaliable via solidity. we don't reinvent / reimplement this in Rain -->