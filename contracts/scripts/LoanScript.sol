// File: contracts/scripts/LoanScript.sol (Updated with Default Resolution Logic)
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
    function isDelinquent(address user) external view returns (bool);
}

// --- UPDATED INTERFACE ---
interface IReputationClaimToken {
    // The `promiseId` is now a required parameter for minting
    function mint(uint256 promiseId, address defaulter, address originalLender, uint256 shortfallAmount, address loanContract) external returns (uint256);
    function burn(uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
    // We need to be able to read the claim data from the LoanScript
    function claims(uint256 tokenId) external view returns (uint256 promiseId, address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
}

/**
 * @title LoanScript
 * @dev Updated to include a mechanism for resolving defaults, which allows a borrower
 * to reclaim their staked reputation after settling their debt.
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

    mapping(uint256 => Loan) public loans;

    // --- EVENTS ---

    event LoanRequested(uint256 indexed loanId, address indexed borrower, address indexed lender, uint256 principal);
    event LoanFunded(uint256 indexed loanId);
    event LoanRepaid(uint256 indexed loanId);
    event LoanDefaulted(uint256 indexed loanId, uint256 rctId);
    // --- NEW EVENT ---
    event LoanResolved(uint256 indexed loanId, uint256 indexed rctId);


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

    // --- LOAN LIFECYCLE (No changes to request, fund, or repay) ---

    function requestLoan(
        address lender,
        uint256 principal,
        uint256 interest,
        uint256 duration,
        uint256 reputationStake
    ) external {
        address borrower = msg.sender;
        uint256 deadline = block.timestamp + duration;
        require(!rainReputation.isDelinquent(borrower), "LoanScript: Borrower is delinquent");
        uint256 actionId = calculusEngine.monitoredAction(borrower);
        uint256 lenderPromiseId = calculusEngine.monitoredPromise(actionId, lender, borrower, address(usdcToken), principal, deadline);
        uint256 borrowerPromiseId = calculusEngine.monitoredPromise(actionId, borrower, lender, address(usdcToken), principal + interest, deadline);
        bytes32 purposeId = bytes32(borrowerPromiseId);
        rainReputation.stake(borrower, reputationStake, purposeId);
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

    function fundLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.lender == msg.sender, "Not the lender");
        require(loan.status == Status.Pending, "Loan not pending");
        (uint256 actionId,,,,,,) = calculusEngine.promises(loanId);
        calculusEngine.monitoredTransfer(actionId, address(usdcToken), loan.lender, loan.borrower, loan.principal);
        calculusEngine.monitoredFulfillment(loan.lenderPromiseId);
        loan.status = Status.Active;
        emit LoanFunded(loanId);
    }

    function repayLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.borrower == msg.sender, "Not the borrower");
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp <= loan.deadline, "Loan past due");
        (uint256 actionId,,,,,,) = calculusEngine.promises(loanId);
        uint256 totalRepayment = loan.principal + loan.interest;
        calculusEngine.monitoredTransfer(actionId, address(usdcToken), loan.borrower, loan.lender, totalRepayment);
        calculusEngine.monitoredFulfillment(loanId);
        rainReputation.releaseStake(bytes32(loanId));
        loan.status = Status.Repaid;
        emit LoanRepaid(loanId);
    }

    // --- UPDATED DEFAULT LOGIC ---

    function claimDefault(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp > loan.deadline, "Deadline not passed");

        // Mark the promise as defaulted. The oracle will see this and slash the score.
        calculusEngine.monitoredDefault(loanId);

        // Mint an RCT to the lender. We now pass the `loanId` so the RCT has a
        // permanent record of the promise it represents.
        // NOTE: We DO NOT release the stake. It is now held hostage by the protocol.
        uint256 rctId = rctContract.mint(loanId, loan.borrower, loan.lender, loan.principal, address(this));

        loan.status = Status.Defaulted;
        emit LoanDefaulted(loanId, rctId);
    }

    // --- NEW DEFAULT RESOLUTION LOGIC ---

    /**
     * @notice Allows the original borrower to resolve their default after they have
     * re-acquired their RCT, enabling them to reclaim their staked reputation.
     * @param rctId The ID of the ReputationClaimToken to be burned.
     */
    function resolveDefault(uint256 rctId) external {
        // 1. Get the data associated with the RCT.
        (uint256 promiseId, address defaulter, , , , ) = rctContract.claims(rctId);

        // 2. Ensure the person calling this function is the original defaulter.
        require(msg.sender == defaulter, "Only the original defaulter can resolve their own debt");

        // 3. Ensure the defaulter now owns the RCT (they bought it back or settled with the lender).
        require(rctContract.ownerOf(rctId) == msg.sender, "You must own the RCT to resolve the default");

        // 4. Burn the RCT. This is the "proof of settlement." The RCT contract will
        //    automatically clear the user's delinquent status if this is their last debt.
        rctContract.burn(rctId);

        // 5. Release the original reputation stake that was held hostage.
        bytes32 purposeId = bytes32(promiseId);
        rainReputation.releaseStake(purposeId);

        emit LoanResolved(promiseId, rctId);
    }
}