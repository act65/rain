// File: contracts/scripts/LoanScript.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// --- INTERFACES FOR CORE PROTOCOL ---

interface ICalculusEngine {
    function monitoredAction(address user) external returns (uint256);
    function monitoredPromise(uint256 actionId, address promisor, address promisee, address asset, uint256 amount, uint256 deadline) external returns (uint256);
    function monitoredTransfer(uint256 actionId, address asset, address from, address to, uint256 amount) external;
    function monitoredFulfillment(uint256 promiseId) external;
    function monitoredDefault(uint256 promiseId) external;
}

interface IRainReputation {
    function stake(address user, uint256 amount, bytes32 purposeId) external;
    function releaseStake(bytes32 purposeId) external;
    function forfeitStake(bytes32 purposeId) external;
    function isDelinquent(address user) external view returns (bool);
}

interface IReputationClaimToken {
    function mint(uint256 promiseId) external returns (uint256);
    function burn(uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
    function claims(uint256 tokenId) external view returns (uint256 promiseId, address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

/**
 * @title LoanScript
 * @dev A reference application: a fixed-term loan secured by a reputation bond.
 *
 * Lifecycle
 *   requestLoan  (borrower) bonds reputation and names a lender.           -> Requested
 *   cancelLoan   (borrower) withdraws an unfunded request; bond returned.  -> Cancelled
 *   fundLoan     (lender)   pays the principal. Only now does the borrower's
 *                           promise to repay exist (and the fee get paid),
 *                           and the term starts counting.                  -> Active
 *   repayLoan    (borrower) pays principal + interest; bond returned.      -> Repaid
 *   claimDefault (anyone)   after the deadline: the promise is Defaulted,
 *                           the bond is forfeited (destroyed), and the
 *                           lender receives an RCT for the amount owed.    -> Defaulted
 *   resolveDefault (borrower) burns the re-acquired RCT, which clears the
 *                           delinquent status. The forfeited bond is gone.
 *
 * Before using this script a borrower must, for this script's address:
 *   CalculusEngine.setScriptAuthorization (to make promises in their name),
 *   CalculusEngine.approveScript for the currency (protocol fee + repayment),
 *   RainReputation.approveStake (the bond),
 * and a lender must CalculusEngine.approveScript the principal.
 */
contract LoanScript {

    ICalculusEngine public immutable calculusEngine;
    IRainReputation public immutable rainReputation;
    IReputationClaimToken public immutable rctContract;
    address public immutable usdcToken;

    enum Status { None, Requested, Active, Repaid, Defaulted, Cancelled }

    struct Loan {
        address borrower;
        address lender;
        uint256 principal;
        uint256 interest;
        uint256 reputationStake;
        uint256 duration;
        uint256 deadline;   // set when the loan is funded
        uint256 promiseId;  // the borrower's promise to repay; set when the loan is funded
        Status status;
    }

    uint256 public loanCount;
    mapping(uint256 => Loan) public loans;
    mapping(uint256 => uint256) public loanForPromise; // promiseId => loanId

    event LoanRequested(uint256 indexed loanId, address indexed borrower, address indexed lender, uint256 principal);
    event LoanCancelled(uint256 indexed loanId);
    event LoanFunded(uint256 indexed loanId, uint256 indexed promiseId, uint256 deadline);
    event LoanRepaid(uint256 indexed loanId);
    event LoanDefaulted(uint256 indexed loanId, uint256 rctId);
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
        usdcToken = _usdcTokenAddress;
    }

    function requestLoan(
        address lender,
        uint256 principal,
        uint256 interest,
        uint256 duration,
        uint256 reputationStake
    ) external returns (uint256 loanId) {
        address borrower = msg.sender;
        require(lender != borrower, "LoanScript: Cannot borrow from yourself");
        require(!rainReputation.isDelinquent(borrower), "LoanScript: Borrower is delinquent");

        loanId = ++loanCount;
        rainReputation.stake(borrower, reputationStake, bytes32(loanId));
        loans[loanId] = Loan({
            borrower: borrower,
            lender: lender,
            principal: principal,
            interest: interest,
            reputationStake: reputationStake,
            duration: duration,
            deadline: 0,
            promiseId: 0,
            status: Status.Requested
        });
        emit LoanRequested(loanId, borrower, lender, principal);
    }

    function cancelLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.borrower == msg.sender, "Not the borrower");
        require(loan.status == Status.Requested, "Loan not requested");
        loan.status = Status.Cancelled;
        rainReputation.releaseStake(bytes32(loanId));
        emit LoanCancelled(loanId);
    }

    function fundLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.lender == msg.sender, "Not the lender");
        require(loan.status == Status.Requested, "Loan not requested");
        require(!rainReputation.isDelinquent(loan.borrower), "LoanScript: Borrower is delinquent");

        loan.status = Status.Active;
        loan.deadline = block.timestamp + loan.duration;

        uint256 actionId = calculusEngine.monitoredAction(loan.borrower);
        // The borrower's promise to repay. The engine charges the borrower the protocol fee.
        loan.promiseId = calculusEngine.monitoredPromise(
            actionId, loan.borrower, loan.lender, usdcToken, loan.principal + loan.interest, loan.deadline
        );
        loanForPromise[loan.promiseId] = loanId;
        calculusEngine.monitoredTransfer(actionId, usdcToken, loan.lender, loan.borrower, loan.principal);

        emit LoanFunded(loanId, loan.promiseId, loan.deadline);
    }

    function repayLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.borrower == msg.sender, "Not the borrower");
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp <= loan.deadline, "Loan past due");

        loan.status = Status.Repaid;
        uint256 actionId = calculusEngine.monitoredAction(loan.borrower);
        calculusEngine.monitoredTransfer(actionId, usdcToken, loan.borrower, loan.lender, loan.principal + loan.interest);
        calculusEngine.monitoredFulfillment(loan.promiseId);
        rainReputation.releaseStake(bytes32(loanId));
        emit LoanRepaid(loanId);
    }

    function claimDefault(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp > loan.deadline, "Deadline not passed");

        loan.status = Status.Defaulted;
        // Mark the promise as defaulted. The oracle will see this and reduce the score.
        calculusEngine.monitoredDefault(loan.promiseId);
        // The bond is lost: this is the part of the penalty that scales with the loan.
        rainReputation.forfeitStake(bytes32(loanId));
        // The lender receives a claim for the amount promised; the borrower becomes delinquent.
        uint256 rctId = rctContract.mint(loan.promiseId);

        emit LoanDefaulted(loanId, rctId);
    }

    /**
     * @notice Lets the defaulter clear their name once they have re-acquired the RCT
     * (i.e. settled with whoever held the claim). They must first approve this
     * contract to burn the RCT.
     */
    function resolveDefault(uint256 rctId) external {
        (uint256 promiseId, address defaulter, , , , address script) = rctContract.claims(rctId);
        require(script == address(this), "LoanScript: Not a claim from this script");
        require(msg.sender == defaulter, "Only the original defaulter can resolve their own debt");
        require(rctContract.ownerOf(rctId) == msg.sender, "You must own the RCT to resolve the default");

        // Burning the RCT clears the delinquent status if this was the user's last debt.
        rctContract.burn(rctId);

        emit LoanResolved(loanForPromise[promiseId], rctId);
    }
}
