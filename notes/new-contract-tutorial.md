Excellent idea. This is the perfect way to tie the entire architecture together. A developer tutorial makes the abstract concepts of the "Free Market" and "Perfect Information" concrete and actionable.

This new document will serve as the primary guide for any developer wanting to build on your protocol. It effectively absorbs and replaces the need for `contract-free-market.md` by putting its philosophy into practice.

Here is the new tutorial.

---

### **Building on Rain: A Developer's Guide to the Free Market**

#### **1. The Core Philosophy: Perfect Information, Not Protection**

Welcome to building on Rain. Before you write a single line of code, you must understand the core philosophy that underpins the entire protocol.

The Rain Protocol is not a "safety net." Its purpose is not to protect users from making bad decisions. Its purpose is to provide them with such **perfect, immutable information** that they are empowered to protect themselves.

The protocol makes only three guarantees:

1.  **An Immutable Log of Promises:** The `CalculusEngine` will perfectly record every economic promise made.
2.  **An Incorruptible Reputation Ledger:** The `RainReputation` contract will ensure every user's score is a mathematically precise reflection of their history of fulfilling or breaking those promises.
3.  **An Inescapable Consequence:** Every default will automatically result in a reputation slash and the creation of a verifiable debt asset (the `ReputationClaimToken`).

The protocol has **zero opinion** on what constitutes a "good" or "bad" loan. It does not set interest rates or collateralization ratios. It is a neutral, unbiased machine for enforcing agreements and recording history.

As a developer, your job is not to find loopholes in the protocol, but to build **trustworthy scripts** that users can confidently interact with.

#### **2. Your Developer Toolkit**

To build an application, you will primarily interact with two core contracts:

*   **`CalculusEngine.sol`:** The Universal Scribe.
    *   `monitoredAction(user)`: The fee-gated entry point for all economic sessions.
    *   `monitoredPromise(...)`: To create a verifiable promise.
    *   `monitoredTransfer(...)`: To move ERC20 tokens.
    *   `monitoredNftTransfer(...)`: To move ERC721 tokens (like RCTs).
    *   `monitoredFulfillment(...)`: To mark a promise as kept.
    *   `monitoredDefault(...)`: To mark a promise as broken.

*   **`RainReputation.sol`:** The Reputation Ledger.
    *   `stake(user, amount, purposeId)`: To lock a user's reputation as collateral.
    *   `releaseStake(purposeId)`: To unlock the reputation once the purpose is fulfilled.

#### **3. Walkthrough: Building a `Good` Loan Script**

Let's build a simplified `LoanScript.sol`. This script will facilitate a loan between a `lender` and a `borrower`, secured by the borrower's staked reputation.

**Step 1: Requesting the Loan & Paying the Fee**

The entire process must begin with a `monitoredAction`. This is how the protocol ensures a fee is paid and a verifiable session is created.

```solidity
// In your LoanScript.sol
contract LoanScript {
    CalculusEngine _calculusEngine;
    RainReputation _rainReputation;
    // ... constructor to set addresses

    function requestLoan(address lender, uint256 principal, uint256 interest, uint256 reputationStake) external {
        address borrower = msg.sender;

        // 1. Create the fee-paid action. The borrower pays the fee.
        uint256 actionId = _calculusEngine.monitoredAction(borrower);

        // 2. Create promises for both parties, linked to the actionId.
        uint256 lenderPromiseId = _calculusEngine.monitoredPromise(actionId, lender, ...);
        uint256 borrowerPromiseId = _calculusEngine.monitoredPromise(actionId, borrower, ...);

        // 3. Stake the borrower's reputation, using the borrower's promise as the purpose.
        // This creates a direct link: this stake exists ONLY to secure this specific promise.
        bytes32 purposeId = bytes32(borrowerPromiseId);
        _rainReputation.stake(borrower, reputationStake, purposeId);
    }
}
```

**Step 2: Funding the Loan**

The lender funds the loan. Your script orchestrates the transfer and marks the lender's promise as fulfilled.

```solidity
// In your LoanScript.sol
function fundLoan(uint256 lenderPromiseId, uint256 principal) external {
    // ... checks to ensure msg.sender is the correct lender ...

    // 1. Get the actionId from the promise.
    uint256 actionId = _calculusEngine.promises(lenderPromiseId).actionId;
    address borrower = _calculusEngine.promises(lenderPromiseId).promisee;

    // 2. Transfer the principal.
    _calculusEngine.monitoredTransfer(actionId, address(usdcToken), msg.sender, borrower, principal);

    // 3. Mark the lender's promise as fulfilled.
    _calculusEngine.monitoredFulfillment(lenderPromiseId);
}
```

**Step 3: Repaying the Loan**

The borrower repays the loan. Your script handles the repayment and fulfills the borrower's promise, releasing their stake.

```solidity
// In your LoanScript.sol
function repayLoan(uint256 borrowerPromiseId, uint256 totalRepayment) external {
    // ... checks ...
    uint256 actionId = _calculusEngine.promises(borrowerPromiseId).actionId;
    address lender = _calculusEngine.promises(borrowerPromiseId).promisee;

    // 1. Transfer the repayment.
    _calculusEngine.monitoredTransfer(actionId, address(usdcToken), msg.sender, lender, totalRepayment);

    // 2. Mark the borrower's promise as fulfilled.
    _calculusEngine.monitoredFulfillment(borrowerPromiseId);

    // 3. Release the reputation stake.
    bytes32 purposeId = bytes32(borrowerPromiseId);
    _rainReputation.releaseStake(purposeId);
}
```

**Step 4: Handling a Default**

If the loan deadline passes and the borrower has not repaid, anyone can trigger the default.

```solidity
// In your LoanScript.sol
function claimDefault(uint256 borrowerPromiseId) external {
    // ... checks to ensure deadline has passed ...

    // Mark the promise as defaulted in the CalculusEngine.
    // The off-chain oracle will see this and slash the borrower's reputation.
    _calculusEngine.monitoredDefault(borrowerPromiseId);

    // Note: We DO NOT release the stake. It remains locked. The lender will
    // receive an RCT, and the resolution of that debt is handled outside this script.
}
```

#### **4. The Free Market: How to Write a `Bad` Loan Script**

The protocol will not stop you from writing a bad script. It will simply record your actions perfectly for all to see. This is the essence of the free market.

*   **Bad Script #1: The "No Stake" Loan**
    You could write a `requestLoan` function that *forgets* to call `_rainReputation.stake()`. The `CalculusEngine` will happily record the promises.
    *   **Why it's bad:** It offers no collateral to the lender beyond the borrower's abstract desire to not have their score slashed.
    *   **The Market's Defense:** A savvy lender will read your script's code, see that it doesn't stake reputation, and **refuse to use it.**

*   **Bad Script #2: The "Instant Default" Loan**
    You could write a `requestLoan` function where the `deadline` for the borrower's promise is `block.timestamp + 1`.
    *   **Why it's bad:** It gives the borrower no time to repay, making a default almost certain. It's a trap.
    *   **The Market's Defense:** The `CalculusEngine` will record this deadline perfectly. A user's wallet interface can read this data, show them "Warning: Loan is due in 1 second," and they will refuse the loan.

In this ecosystem, **transparency is the security model.** Your code is your reputation.

#### **5. Conclusion**

As a developer on Rain, you are a participant in a free market for trust. The protocol provides the tools to create secure, verifiable agreements. It does not, however, enforce good business logic. That is your responsibility.

Build transparently. Build logically. Build scripts that you would be confident to use yourself. In the Rain ecosystem, the most trustworthy scripts will attract the most users, and the market will abandon those that are poorly or maliciously designed.