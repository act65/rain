// File: contracts/scripts/LoanScript.sol (Updated with Delinquency Check)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// --- INTERFACES FOR CORE PROTOCOL ---

interface ICalculusEngine {
    function monitoredAction(address user) external returns (uint256);
    function monitoredPromise(uint256 actionId, address promisor, address promisee, address asset, uint256 amount, uint256 deadline) external returns (uint256);
    function monitoredTransfer(uint256 actionId, address asset, address from, address to, uint256 amount) external;
    function monitoredFulfillment(uint256 promiseId) external;
    function monitoredDefault(uint256 promiseId) external;
    function promises(uint256 promiseId) external view returns (uint256 actionId, address promisor, address promisee, address asset, uint256 amount, uint256 deadline, uint8 status);
}

interface IRainReputation {
    function stake(address user, uint256 amount, bytes32 purposeId) external;
    function releaseStake(bytes32 purposeId) external;
    // --- NEW: Add isDelinquent to the interface ---
    function isDelinquent(address user) external view returns (bool);
}

interface IReputationClaimToken {
    function mint(address defaulter, address originalLender, uint256 shortfallAmount, address loanContract) external returns (uint256);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
}

/**
 * @title LoanScript
 * @author Rain Protocol
 * @dev An example application built on the Rain Protocol eDSL. This script facilitates
 * a simple, reputation-staked, peer-to-peer loan. It demonstrates how to compose
 * the core primitives to create a useful financial product.
 */
contract LoanScript {

    // --- STATE ---

    ICalculusEngine public immutable calculusEngine;
    IRainReputation public immutable rainReputation;
    IReputationClaimToken public immutable rctContract;
    IERC20 public immutable usdcToken;

    enum Status { Pending, Active, Repaid, Defaulted }

    struct Loan {
        address borrower;
        address lender;
        uint256 principal;
        uint256 interest;
        uint256 reputationStake;
        uint256 deadline;
        uint256 lenderPromiseId;
        Status status;
    }

    // The loanId is the borrower's promiseId from the CalculusEngine
    mapping(uint256 => Loan) public loans;

    // --- EVENTS ---

    event LoanRequested(uint256 indexed loanId, address indexed borrower, address indexed lender, uint256 principal);
    event LoanFunded(uint256 indexed loanId);
    event LoanRepaid(uint256 indexed loanId);
    event LoanDefaulted(uint256 indexed loanId, uint256 rctId);

    // --- SETUP ---

    constructor(
        address _calculusEngineAddress,
        address _rainReputationAddress,
        address _rctContractAddress,
        address _usdcTokenAddress
    ) {
        calculusEngine = ICalculusEngine(_calculusEngineAddress);
        rainReputation = IRainReputation(_rainReputationAddress);
        rctContract = IReputationClaimToken(_rctContractAddress);
        usdcToken = IERC20(_usdcTokenAddress);
    }

    // --- LOAN LIFECYCLE ---

    /**
     * @notice Borrower initiates a loan request.
     * @dev This function orchestrates the first set of eDSL primitives: creating the
     * action, logging the promises, and staking the reputation collateral.
     */
    function requestLoan(
        address lender,
        uint256 principal,
        uint256 interest,
        uint256 duration, // in seconds
        uint256 reputationStake
    ) external {
        address borrower = msg.sender;
        uint256 deadline = block.timestamp + duration;

        // --- NEW: Risk Management Check ---
        // This is the application's responsibility: check the information provided
        // by the core protocol before proceeding.
        require(!rainReputation.isDelinquent(borrower), "LoanScript: Borrower is delinquent");

        // 1. Start the economic session by calling the interpreter's entry point.
        uint256 actionId = calculusEngine.monitoredAction(borrower);

        // 2. Create the two core promises, linked to the actionId.
        uint256 lenderPromiseId = calculusEngine.monitoredPromise(actionId, lender, borrower, address(usdcToken), principal, deadline);
        uint256 borrowerPromiseId = calculusEngine.monitoredPromise(actionId, borrower, lender, address(usdcToken), principal + interest, deadline);

        // 3. Stake the borrower's reputation, using their promiseId as the unique purpose.
        // This creates an unbreakable on-chain link between the stake and the debt.
        bytes32 purposeId = bytes32(borrowerPromiseId);
        rainReputation.stake(borrower, reputationStake, purposeId);

        // 4. Store the loan details in our script's local state.
        loans[borrowerPromiseId] = Loan({
            borrower: borrower,
            lender: lender,
            principal: principal,
            interest: interest,
            reputationStake: reputationStake,
            deadline: deadline,
            lenderPromiseId: lenderPromiseId,
            status: Status.Pending
        });

        emit LoanRequested(borrowerPromiseId, borrower, lender, principal);
    }

    /**
     * @notice Lender funds the loan.
     * @param loanId The ID of the loan, which is the borrower's promiseId.
     */
    function fundLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.lender == msg.sender, "Not the lender");
        require(loan.status == Status.Pending, "Loan not pending");

        // The lender must have approved the CalculusEngine to spend their USDC.
        // This is done in the user's wallet, not in this contract.

        // Get the actionId from the promise stored in the engine.
        (uint256 actionId,,,,,,) = calculusEngine.promises(loanId);

        // Use the eDSL to transfer funds and fulfill the lender's promise.
        calculusEngine.monitoredTransfer(actionId, address(usdcToken), loan.lender, loan.borrower, loan.principal);
        calculusEngine.monitoredFulfillment(loan.lenderPromiseId);

        loan.status = Status.Active;
        emit LoanFunded(loanId);
    }

    /**
     * @notice Borrower repays the loan.
     * @param loanId The ID of the loan.
     */
    function repayLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.borrower == msg.sender, "Not the borrower");
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp <= loan.deadline, "Loan past due");

        // The borrower must have approved the CalculusEngine for the full repayment amount.
        (uint256 actionId,,,,,,) = calculusEngine.promises(loanId);
        uint256 totalRepayment = loan.principal + loan.interest;

        // Use the eDSL to transfer repayment, fulfill the promise, and release the stake.
        calculusEngine.monitoredTransfer(actionId, address(usdcToken), loan.borrower, loan.lender, totalRepayment);
        calculusEngine.monitoredFulfillment(loanId); // Fulfill the borrower's promise
        rainReputation.releaseStake(bytes32(loanId));

        loan.status = Status.Repaid;
        emit LoanRepaid(loanId);
    }

    /**
     * @notice Anyone can declare a loan as defaulted after the deadline has passed.
     * @param loanId The ID of the loan.
     */
    function claimDefault(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp > loan.deadline, "Deadline not passed");

        // Use the eDSL to mark the promise as defaulted. The oracle will see this.
        calculusEngine.monitoredDefault(loanId);

        // As the script that witnessed the default, we mint an RCT to the lender.
        // The shortfall is the principal the lender lost.
        uint256 rctId = rctContract.mint(loan.borrower, loan.lender, loan.principal, address(this));

        loan.status = Status.Defaulted;
        emit LoanDefaulted(loanId, rctId);
    }
}