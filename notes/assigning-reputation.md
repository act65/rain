### **Assigning Reputation: The Atomic Action & Promise Integrity Model**

#### **Abstract**

The credibility of a decentralized economy rests on the fairness and exploit-resistance of its reputation system. This document outlines the Rain Protocol's definitive model for assigning reputation. We have deliberately chosen to anchor reputation to a single, incorruptible metric: **Promise Integrity**. This is achieved through the **Atomic Action Framework**, where a universal `CalculusEngine` creates an immutable log of all promises and their outcomes. An off-chain oracle analyzes this log to assign reputation, creating a system that is objective, transparent, and economically secure by design.

---

#### **1. The Core Principle: Promise Integrity over Economic Surplus**

Early models considered calculating the "economic surplus" or "value delta" of an interaction to assign reputation. We have rejected this approach. Calculating surplus is complex, subjective, and invites edge cases and economic exploits.

Instead, our model is founded on a simpler, more powerful principle. Reputation is a measure of **trustworthiness**, and the most direct, objective measure of trustworthiness is whether a user **keeps their promises**.

*   A user who verifiably fulfills their commitments is trustworthy and **gains** reputation.
*   A user who verifiably breaks their commitments is untrustworthy and **loses** reputation.

This binary, verifiable standard is the bedrock of our reputation assignment model.

---

#### **2. The Atomic Action Framework: The Immutable Log**

To measure promise integrity, we need a perfect, unchangeable record of all promises made. The `CalculusEngine.sol` contract serves this purpose, acting as a "Universal Scribe" for the ecosystem. It does not interpret actions; it simply records them through a set of constrained primitives.

1.  **`monitoredAction(user)`:** The single, mandatory gateway for any economic session. It charges a `protocolFee` from the `user` and creates a unique `actionId`. This ensures that no promise can be made without a verifiable economic cost.
2.  **`monitoredPromise(actionId, ...)`:** Creates a future obligation (e.g., "Alice promises to pay Bob 100 DMD by next Tuesday"). This promise is now cryptographically linked to the fee-paid `actionId`.
3.  **`monitoredFulfillment(promiseId)`:** Called by the orchestrating script when a promise has been verifiably kept.
4.  **`monitoredDefault(promiseId)`:** Called by the orchestrating script when a promise's deadline has passed and it has not been kept.

The `CalculusEngine` produces an immutable, on-chain log of `PromiseCreated`, `PromiseFulfilled`, and `PromiseDefaulted` events, providing all the raw data needed for reputation assignment.

---

#### **3. The Off-Chain Oracle and The Rules Engine**

The actual calculation of reputation changes happens off-chain for maximum flexibility and gas efficiency.

1.  **The Oracle:** A decentralized oracle service continuously reads the event log from the `CalculusEngine`.
2.  **The Rules Engine:** The oracle applies a simple, transparent set of rules to this data:
    *   **If `PromiseFulfilled` event is observed for `promiseId`:** The `promisor` gains a fixed amount of reputation.
    *   **If `PromiseDefaulted` event is observed for `promiseId`:** The `promisor` loses a significant amount of reputation. The penalty is deliberately severe to create a powerful economic deterrent.
    *   **Other Actions:** Actions that do not involve promises (e.g., a simple `monitoredTransfer`) **do not result in any reputation change.** Reputation is earned *only* by making and keeping promises.

---

#### **4. Committing to the Ledger: The `ReputationUpdater`**

Once the oracle's Rules Engine has calculated the reputation changes, it sends them to the `ReputationUpdater.sol` contract. This contract holds the `UPDATER_ROLE` and is the only entity authorized to call the `increaseReputation` or `slash` functions on the `RainReputation.sol` contract, committing the final changes to the on-chain ledger.

---

#### **5. Security Analysis: Resisting Exploitation**

This model is designed to be resistant to the most common reputation attacks.

**Attack Vector 1: Reputation Farming**
*   **The Attack:** An attacker tries to gain reputation for free by creating and fulfilling meaningless promises to themselves or a colluding partner.
*   **The Defense: The Inescapable Fee.** Every promise must be created within a `monitoredAction` that charges a non-refundable `protocolFee`. The system is designed to ensure the economic value of the reputation gained from a simple, fulfilled promise is *always less* than the fee paid to create it.
    *   **Example:** An attacker pays a **$0.10** fee to the `CalculusEngine`. They create a promise to send themselves 1 wei, and then fulfill it. They gain a small amount of reputation. However, the economic value of this reputation (in future dividends, as explained in the *Valuing Reputation* document) is designed to be worth, for example, **$0.01**. The attacker has just paid $0.10 to earn $0.01. The attack is unprofitable by design.

**The Dynamic Fee Consideration**
Your insight is correct: if the value of reputation changes (e.g., the Treasury grows), a static fee could become exploitable.
*   **The Solution:** The `protocolFee` in the `CalculusEngine` is not immutable. It is a parameter that can be adjusted by protocol governance (the DAO). The DAO's primary responsibility is to monitor the economic value of reputation and adjust the `protocolFee` periodically to ensure the `Cost of Action > Value of Reputation Gain` inequality always holds true.

**Attack Vector 2: Wash Trading / Collusion**
*   **The Attack:** Two attackers, Alice and Bob, create large, offsetting loans to each other to generate the appearance of significant economic activity.
*   **The Defense:** This attack is defeated by the same mechanism. For Alice and Bob to fulfill their promises to each other, they must each initiate a `monitoredAction` and pay the `protocolFee`. They are simply paying double the fees for no net gain, making the wash trade a guaranteed net loss. The system is indifferent to *who* is making the promise; it only cares that a fee was paid and the promise was kept.