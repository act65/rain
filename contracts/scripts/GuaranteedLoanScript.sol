// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IEngine {
    function monitoredAction(address user) external returns (uint256);
    function monitoredPromise(uint256 actionId, address promisor, address promisee, address asset, uint256 amount, uint256 deadline) external returns (uint256);
    function monitoredTransfer(uint256 actionId, address asset, address from, address to, uint256 amount) external;
    function monitoredFulfillment(uint256 promiseId) external;
    function monitoredDefault(uint256 promiseId) external;
}

interface IReputation {
    function isDelinquent(address user) external view returns (bool);
}

interface IClaimToken {
    function mint(uint256 promiseId) external returns (uint256);
    function burn(uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
    function claims(uint256 tokenId) external view returns (uint256 promiseId, address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

/**
 * @title GuaranteedLoanScript
 * @dev A reference application: a loan that someone else answers for (vouching).
 *
 * A newcomer has no record a lender can rely on. A guarantor who does can put their own
 * standing behind the newcomer. The loan is recorded as two promises of the amount due:
 *
 *   the borrower promises the guarantor   (deadline: the end of the term)
 *   the guarantor promises the lender     (deadline: the end of the term + a grace period)
 *
 * The lender's money goes straight to the borrower, and the borrower's repayment straight to
 * the lender, which keeps both promises. If the borrower does not repay, their promise is
 * broken and the claim on them goes to the guarantor, who then has the grace period to pay
 * the lender. If the guarantor does not, their promise is broken too and the lender holds a
 * claim on the guarantor.
 *
 * So the lender is relying on the guarantor's record, not the borrower's, and the guarantor
 * bears the loss if they vouched for the wrong person. The borrower's repayments are on the
 * log as promises kept to the guarantor: how much they say about the borrower is for each
 * reader to judge, knowing who the guarantor is to them (see rain/record.py).
 *
 * Lifecycle
 *   requestLoan           (borrower)  names a lender and a guarantor.            -> Requested
 *   guarantee             (guarantor) agrees to answer for it.                   -> Guaranteed
 *   cancelLoan            (borrower or guarantor) before it is funded.           -> Cancelled
 *   fundLoan              (lender)    pays the principal; both promises are
 *                                     recorded and both promisors pay the fee.   -> Active
 *   repayLoan             (borrower)  pays the lender; both promises kept.       -> Repaid
 *   claimDefault          (anyone)    after the deadline: the borrower's promise
 *                                     is broken; the guarantor receives the RCT. -> Called
 *   coverLoan             (guarantor) within the grace period pays the lender;
 *                                     the guarantor's promise is kept.           -> Covered
 *   claimGuarantorDefault (anyone)    after the grace period: the guarantor's
 *                                     promise is broken; the lender receives an
 *                                     RCT against the guarantor.                 -> GuarantorDefaulted
 *   resolveDefault        (a defaulter) burns their re-acquired RCT.
 *
 * Borrower and guarantor must each have authorized this script on the CalculusEngine and
 * approved it for the currency (the fee, and what they may have to pay). The lender must
 * have approved it for the principal.
 */
contract GuaranteedLoanScript {

    IEngine public immutable calculusEngine;
    IReputation public immutable rainReputation;
    IClaimToken public immutable rctContract;
    address public immutable usdcToken;

    enum Status { None, Requested, Guaranteed, Active, Repaid, Called, Covered, GuarantorDefaulted, Cancelled }

    struct Loan {
        address borrower;
        address guarantor;
        address lender;
        uint256 principal;
        uint256 interest;
        uint256 duration;
        uint256 gracePeriod;
        uint256 deadline;            // the borrower's; set when the loan is funded
        uint256 borrowerPromiseId;   // borrower -> guarantor
        uint256 guarantorPromiseId;  // guarantor -> lender
        Status status;
    }

    uint256 public loanCount;
    mapping(uint256 => Loan) public loans;
    mapping(uint256 => uint256) public loanForPromise; // either promise => loanId

    event LoanRequested(uint256 indexed loanId, address indexed borrower, address indexed guarantor, address lender, uint256 principal);
    event LoanGuaranteed(uint256 indexed loanId);
    event LoanCancelled(uint256 indexed loanId);
    event LoanFunded(uint256 indexed loanId, uint256 borrowerPromiseId, uint256 guarantorPromiseId, uint256 deadline);
    event LoanRepaid(uint256 indexed loanId);
    event GuaranteeCalled(uint256 indexed loanId, uint256 rctId);
    event LoanCovered(uint256 indexed loanId);
    event GuarantorDefaulted(uint256 indexed loanId, uint256 rctId);
    event DefaultResolved(uint256 indexed loanId, uint256 indexed rctId);

    constructor(address _calculusEngine, address _rainReputation, address _rctContract, address _usdcToken) {
        calculusEngine = IEngine(_calculusEngine);
        rainReputation = IReputation(_rainReputation);
        rctContract = IClaimToken(_rctContract);
        usdcToken = _usdcToken;
    }

    function requestLoan(
        address lender,
        address guarantor,
        uint256 principal,
        uint256 interest,
        uint256 duration,
        uint256 gracePeriod
    ) external returns (uint256 loanId) {
        address borrower = msg.sender;
        require(lender != borrower && guarantor != borrower && guarantor != lender, "GuaranteedLoan: Needs three parties");
        require(!rainReputation.isDelinquent(borrower), "GuaranteedLoan: Borrower is delinquent");

        loanId = ++loanCount;
        Loan storage loan = loans[loanId];
        loan.borrower = borrower;
        loan.guarantor = guarantor;
        loan.lender = lender;
        loan.principal = principal;
        loan.interest = interest;
        loan.duration = duration;
        loan.gracePeriod = gracePeriod;
        loan.status = Status.Requested;
        emit LoanRequested(loanId, borrower, guarantor, lender, principal);
    }

    function guarantee(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.guarantor == msg.sender, "Not the guarantor");
        require(loan.status == Status.Requested, "Loan not requested");
        loan.status = Status.Guaranteed;
        emit LoanGuaranteed(loanId);
    }

    function cancelLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.borrower || msg.sender == loan.guarantor, "Not the borrower or the guarantor");
        require(loan.status == Status.Requested || loan.status == Status.Guaranteed, "Loan already funded or closed");
        loan.status = Status.Cancelled;
        emit LoanCancelled(loanId);
    }

    function fundLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.lender == msg.sender, "Not the lender");
        require(loan.status == Status.Guaranteed, "Loan not guaranteed");
        require(!rainReputation.isDelinquent(loan.borrower), "GuaranteedLoan: Borrower is delinquent");
        require(!rainReputation.isDelinquent(loan.guarantor), "GuaranteedLoan: Guarantor is delinquent");

        loan.status = Status.Active;
        loan.deadline = block.timestamp + loan.duration;
        uint256 due = loan.principal + loan.interest;

        uint256 actionId = calculusEngine.monitoredAction(loan.borrower);
        loan.borrowerPromiseId = calculusEngine.monitoredPromise(
            actionId, loan.borrower, loan.guarantor, usdcToken, due, loan.deadline
        );
        loan.guarantorPromiseId = calculusEngine.monitoredPromise(
            actionId, loan.guarantor, loan.lender, usdcToken, due, loan.deadline + loan.gracePeriod
        );
        loanForPromise[loan.borrowerPromiseId] = loanId;
        loanForPromise[loan.guarantorPromiseId] = loanId;
        calculusEngine.monitoredTransfer(actionId, usdcToken, loan.lender, loan.borrower, loan.principal);

        emit LoanFunded(loanId, loan.borrowerPromiseId, loan.guarantorPromiseId, loan.deadline);
    }

    function repayLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.borrower == msg.sender, "Not the borrower");
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp <= loan.deadline, "Loan past due");

        loan.status = Status.Repaid;
        uint256 actionId = calculusEngine.monitoredAction(loan.borrower);
        calculusEngine.monitoredTransfer(actionId, usdcToken, loan.borrower, loan.lender, loan.principal + loan.interest);
        calculusEngine.monitoredFulfillment(loan.borrowerPromiseId);
        calculusEngine.monitoredFulfillment(loan.guarantorPromiseId);
        emit LoanRepaid(loanId);
    }

    /// @notice After the borrower's deadline: their promise is broken and the guarantor is called on.
    function claimDefault(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.status == Status.Active, "Loan not active");
        require(block.timestamp > loan.deadline, "Deadline not passed");

        loan.status = Status.Called;
        calculusEngine.monitoredDefault(loan.borrowerPromiseId);
        // The claim on the borrower goes to the guarantor (the promisee), who is about to pay for them.
        uint256 rctId = rctContract.mint(loan.borrowerPromiseId);
        emit GuaranteeCalled(loanId, rctId);
    }

    /// @notice The guarantor pays the lender what the borrower owed.
    function coverLoan(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.guarantor == msg.sender, "Not the guarantor");
        require(loan.status == Status.Called, "Guarantee not called");
        require(block.timestamp <= loan.deadline + loan.gracePeriod, "Grace period over");

        loan.status = Status.Covered;
        uint256 actionId = calculusEngine.monitoredAction(loan.guarantor);
        calculusEngine.monitoredTransfer(actionId, usdcToken, loan.guarantor, loan.lender, loan.principal + loan.interest);
        calculusEngine.monitoredFulfillment(loan.guarantorPromiseId);
        emit LoanCovered(loanId);
    }

    /// @notice After the grace period: the guarantor's promise is broken and the lender holds a claim on them.
    function claimGuarantorDefault(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(loan.status == Status.Called, "Guarantee not called");
        require(block.timestamp > loan.deadline + loan.gracePeriod, "Grace period not over");

        loan.status = Status.GuarantorDefaulted;
        calculusEngine.monitoredDefault(loan.guarantorPromiseId);
        uint256 rctId = rctContract.mint(loan.guarantorPromiseId);
        emit GuarantorDefaulted(loanId, rctId);
    }

    /// @notice A defaulter (borrower or guarantor) clears a claim they have re-acquired. They must first approve this contract to burn it.
    function resolveDefault(uint256 rctId) external {
        (uint256 promiseId, address defaulter, , , , address script) = rctContract.claims(rctId);
        require(script == address(this), "GuaranteedLoan: Not a claim from this script");
        require(msg.sender == defaulter, "Only the original defaulter can resolve their own debt");
        require(rctContract.ownerOf(rctId) == msg.sender, "You must own the RCT to resolve the default");
        rctContract.burn(rctId);
        emit DefaultResolved(loanForPromise[promiseId], rctId);
    }
}
