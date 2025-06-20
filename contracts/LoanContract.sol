// File: contracts/LoanContract.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CurrencyToken.sol";
import "./ReputationSBT.sol";

/**
 * @title LoanContract
 * @dev Manages the lifecycle of reputation-staked loans.
 */
contract LoanContract {
    // --- State Variables ---
    CurrencyToken public currencyToken;
    ReputationSBT public reputationSBT;

    enum LoanStatus { Pending, Active, Repaid, Defaulted }

    struct Loan {
        uint256 id;
        address borrower;
        address lender;
        uint256 principal;
        uint256 interest;
        uint256 reputationStake;
        uint256 repaymentDeadline;
        LoanStatus status;
    }

    mapping(uint256 => Loan) public loans;
    uint256 public nextLoanId;
    
    // --- Constants for Reputation Changes ---
    uint256 public constant REPUTATION_BOOST_ON_REPAYMENT = 10;

    // --- Events ---
    event LoanRequested(uint256 loanId, address indexed borrower, uint256 principal);
    event LoanFunded(uint256 loanId, address indexed lender);
    event LoanRepaid(uint256 loanId);
    event LoanDefaultClaimed(uint256 loanId);

    // --- Constructor ---
    constructor(address _currencyTokenAddress, address _reputationSBTAddress) {
        currencyToken = CurrencyToken(_currencyTokenAddress);
        reputationSBT = ReputationSBT(_reputationSBTAddress);
    }

    // --- Core Functions ---

    /**
     * @dev A borrower requests a loan, specifying the terms.
     * The reputation stake is calculated based on the principal.
     */
    function requestLoan(uint256 _principal, uint256 _interest, uint256 _repaymentPeriod) external {
        uint256 reputationToStake = _principal / 10; // Example: Stake 10% of principal value in reputation points
        
        // Stake reputation in the SBT contract
        reputationSBT.stake(msg.sender, reputationToStake);

        loans[nextLoanId] = Loan({
            id: nextLoanId,
            borrower: msg.sender,
            lender: address(0), // Lender not yet assigned
            principal: _principal,
            interest: _interest,
            reputationStake: reputationToStake,
            repaymentDeadline: block.timestamp + _repaymentPeriod,
            status: LoanStatus.Pending
        });

        emit LoanRequested(nextLoanId, msg.sender, _principal);
        nextLoanId++;
    }

    /**
     * @dev A lender funds an existing loan request.
     */
    function fundLoan(uint256 _loanId) external {
        Loan storage loan = loans[_loanId];
        require(loan.status == LoanStatus.Pending, "Loan is not pending");
        require(loan.borrower != msg.sender, "Cannot fund your own loan");

        loan.lender = msg.sender;
        loan.status = LoanStatus.Active;

        // Transfer the principal from lender to borrower
        require(currencyToken.transferFrom(msg.sender, loan.borrower, loan.principal), "Token transfer failed");

        emit LoanFunded(_loanId, msg.sender);
    }

    /**
     * @dev The borrower repays the loan.
     */
    function repayLoan(uint256 _loanId) external {
        Loan storage loan = loans[_loanId];
        require(loan.borrower == msg.sender, "Only borrower can repay");
        require(loan.status == LoanStatus.Active, "Loan is not active");

        uint256 totalRepayment = loan.principal + loan.interest;
        
        // Transfer repayment from borrower to lender
        require(currencyToken.transferFrom(msg.sender, loan.lender, totalRepayment), "Repayment transfer failed");

        // Update loan status
        loan.status = LoanStatus.Repaid;

        // Release the reputation stake and boost reputation
        reputationSBT.releaseStake(loan.borrower, loan.reputationStake);
        reputationSBT.increaseReputation(loan.borrower, REPUTATION_BOOST_ON_REPAYMENT);

        emit LoanRepaid(_loanId);
    }

    /**
     * @dev The lender claims a default if the loan is not repaid in time.
     */
    function claimDefault(uint256 _loanId) external {
        Loan storage loan = loans[_loanId];
        require(loan.lender == msg.sender, "Only lender can claim default");
        require(loan.status == LoanStatus.Active, "Loan is not active");
        require(block.timestamp > loan.repaymentDeadline, "Repayment period has not ended");

        loan.status = LoanStatus.Defaulted;

        // Slash the borrower's staked reputation
        reputationSBT.slash(loan.borrower, loan.reputationStake);

        emit LoanDefaultClaimed(_loanId);
    }
}