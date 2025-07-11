### **The Rain Protocol: A Unified Architectural Overview (Updated)**

#### **Abstract**

Rain Protocol is a decentralized digital economy designed to function in both connected and disconnected environments. Its architecture is a layered stack that separates concerns, from decentralized identity at its base to user-facing applications at its peak. This document provides a concise overview of this architecture, detailing the roles of its core smart contracts, the function of its native tokens, and how the layers work in concert to create a secure, self-sustaining, and reputation-based financial ecosystem built on a foundation of **atomic, fee-paid actions**.

---

#### **Layer 0: Decentralized Identity & Trust Root**

This is the foundational layer that establishes who can participate in the economy. It is built on the principle of costly, non-transferable identity to prevent Sybil attacks.

*   **Implementation:** The `RainReputation.sol` contract.
*   **Identity Primitive:** Each user is issued a non-transferable ERC721 token, or **Soulbound Token (SBT)**. This token acts as a permanent, foundational digital identity within the ecosystem. It is earned, not bought or traded.
*   **Sybil Resistance:** The protocol's primitives enable higher-level applications to create robust Sybil resistance mechanisms. For example, a "Web of Trust" application can be built where new users must be sponsored by existing members who co-stake a financial bond using the `RainReputation.stake()` function.

---

#### **Layer 1: The Settlement Layer**

This is the underlying blockchain that serves as the ultimate, immutable source of truth for all transactions and asset ownership.

*   **Implementation:** A low-cost, high-throughput blockchain (e.g., an Ethereum L2 like Arbitrum or Polygon).
*   **Unit of Account:** All economic activity is denominated in a trusted, fiat-backed stablecoin (e.g., USDC), represented by the `CurrencyToken.sol` contract within the protocol.

---

#### **Layer 2: The Agreement Layer (The Protocol Core)**

This is the heart of the protocol, where the rules of the economy are defined and autonomously enforced by a suite of interconnected smart contracts. This layer follows the **Atomic Action Framework**.

*   **The Universal Scribe (`CalculusEngine.sol`):** This is the single, mandatory gateway for all economic activity. Its responsibilities are:
    1.  **Fee-Gated Entry:** Enforcing a protocol fee via its `monitoredAction()` function, ensuring every economic session is paid for.
    2.  **Immutable Log:** Creating a verifiable, on-chain log of all promises (`monitoredPromise`) and value transfers (`monitoredTransfer`, `monitoredNftTransfer`) associated with a fee-paid action.
    3.  **Contextual Linkage:** Cryptographically linking every promise and transfer to a unique `actionId`, creating unambiguous economic sessions.

*   **The Reputation Ledger (`RainReputation.sol`):** This is the unified source of truth for user standing. Its responsibilities are:
    1.  **Identity Management:** Minting the SBTs that anchor Layer 0.
    2.  **Reputation Scoring:** Maintaining the authoritative reputation score for every user.
    3.  **Permissionless Collateral:** Exposing public `stake()` and `releaseStake()` functions that allow any application to lock reputation as collateral for a specific purpose.
    4.  **Gated Updates:** Allowing reputation scores to be modified *only* by a contract holding the `UPDATER_ROLE`.

*   **The Oracle's Hand (`ReputationUpdater.sol`):** This is a simple, highly secure contract that is granted the `UPDATER_ROLE`. It is the only contract that can command the `RainReputation` ledger. It receives the results of the off-chain reputation calculation (which analyzes the `CalculusEngine` log) and commits them on-chain.

*   **The Economic Engine (`TreasuryV2.sol`):** This contract is the protocol's autonomous economic heart. Its responsibilities are:
    1.  **Fee Aggregation:** Acting as the central collection point for all protocol fees generated by the `CalculusEngine`.
    2.  **Yield Generation:** Investing its capital into whitelisted, external DeFi protocols (e.g., Aave) to generate yield.
    3.  **Dividend Distribution:** Distributing this yield back to users as a Reputation Dividend, using a scalable and secure Merkle drop mechanism.

---

#### **Layer 3: The Application Layer**

This is the user-facing layer, consisting of applications ("Scripts") that interact with the Layer 2 primitives to provide services to the end-user.

*   **Implementation:** An offline-first mobile application, third-party loan scripts, etc.
*   **Features:**
    *   **Online Mode:** Functions as a standard crypto wallet, allowing interaction with any application built on the protocol, such as a `LoanScript` that uses the `CalculusEngine` primitives.
    *   **Offline Mode:** A user can stake reputation to have a protocol-authorized key sign a **single-use, offline data packet**. This packet (e.g., a QR code) can be verified by a recipient's device without an internet connection, enabling peer-to-peer commerce.
    *   **"Sneakernet" Syncing:** A dynamic fee market where agents are incentivized to batch and settle these offline signed messages to the Layer 1 blockchain.

---

#### **Tokens of the Ecosystem**

The Rain economy is powered by three core tokens:

1.  **RAIN (Reputation SBT):**
    *   **Type:** Non-transferable ERC721 (Soulbound Token).
    *   **Function:** Represents a user's identity and is the anchor for their reputation score.
    *   **Acquisition:** Granted upon successful entry into the ecosystem; its value (the score) is earned through trustworthy behavior.

2.  **DMD (Demo Dollar - representing USDC):**
    *   **Type:** Standard ERC20.
    *   **Function:** The stable unit of account for the entire economy. Used for all economic transactions, including loan principals, fee payments, and Reputation Dividends.
    *   **Acquisition:** Acquired on the open market.

3.  **RCT (Reputation Claim Token):**
    *   **Type:** Non-fungible ERC721.
    *   **Function:** A securitized debt instrument. It is minted to a lender when a borrower defaults, representing a verifiable claim on that specific debt.
    *   **Acquisition:** Received by a lender upon a borrower's default. It can be held, or sold on a secondary market.