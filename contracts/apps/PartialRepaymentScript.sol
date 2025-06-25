// File: contracts/scripts/PartialRepaymentScript.sol (Corrected, REF-Compliant Version)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "../interfaces/ICalculusEngine.sol";
import "../interfaces/IReputationClaimToken.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title PartialRepaymentScript
 * @author Rain Protocol
 * @dev A REF-compliant script that orchestrates a partial repayment plan.
 * It uses the CalculusEngine for all value transfers and promise tracking.
 * This contract must be granted the BURNER_ROLE on the RCT contract and the
 * SESSION_CREATOR_ROLE on the CalculusEngine.
 */
contract PartialRepaymentScript {
    ICalculusEngine public immutable calculusEngine;
    IReputationClaimToken public immutable rctContract;
    IERC20 public immutable usdcToken;
    uint256 public immutable protocolFee;

    enum PlanStatus { Inactive, Active, Finalized, Cancelled }

    struct RepaymentPlan {
        address creditor;
        address defaulter;
        uint256 totalOwed;
        uint256 amountPaid;
        uint256 actionId; // The session ID from the CalculusEngine
        uint256 masterPromiseId; // The single promise to repay the full amount
        PlanStatus status;
    }

    mapping(uint256 => RepaymentPlan) public repaymentPlans; // Mapping from RCT tokenId to plan

    event PlanInitiated(uint256 indexed tokenId, uint256 indexed actionId, uint256 masterPromiseId);
    event PaymentMade(uint256 indexed tokenId, uint256 amount);
    event PlanFinalized(uint256 indexed tokenId);
    event PlanCancelled(uint256 indexed tokenId);

    constructor(
        address _calculusEngineAddress,
        address _rctContractAddress,
        address _usdcTokenAddress
    ) {
        calculusEngine = ICalculusEngine(_calculusEngineAddress);
        rctContract = IReputationClaimToken(_rctContractAddress);
        usdcToken = IERC20(_usdcTokenAddress);
        // In a real system, the fee would be fetched from a PolicyKernel
        protocolFee = 50000; // 0.05 USDC for this example
    }

    /**
     * @notice Initiated by the RCT holder to place their token into escrow.
     * This creates the session and the master promise in the CalculusEngine.
     */
    function initiatePlan(uint256 tokenId, uint256 deadline) external {
        require(rctContract.ownerOf(tokenId) == msg.sender, "Caller is not the owner of this RCT");
        require(repaymentPlans[tokenId].status == PlanStatus.Inactive, "Plan already exists");

        // The creditor pays the protocol fee to initiate the repayment session
        usdcToken.approve(address(calculusEngine), protocolFee);
        uint256 actionId = calculusEngine.monitoredAction(msg.sender);

        // Transfer the RCT into this contract's custody (this is a control action, not a value one)
        rctContract.transferFrom(msg.sender, address(this), tokenId);

        IReputationClaimToken.DebtClaim memory claim = rctContract.claims(tokenId);

        // Create the single, overarching promise for the defaulter to repay the full amount
        uint256 masterPromiseId = calculusEngine.monitoredPromise(
            actionId,
            claim.defaulterAddress,
            msg.sender, // Promise is to the creditor
            address(usdcToken),
            claim.shortfallAmount,
            deadline
        );

        repaymentPlans[tokenId] = RepaymentPlan({
            creditor: msg.sender,
            defaulter: claim.defaulterAddress,
            totalOwed: claim.shortfallAmount,
            amountPaid: 0,
            actionId: actionId,
            masterPromiseId: masterPromiseId,
            status: PlanStatus.Active
        });

        emit PlanInitiated(tokenId, actionId, masterPromiseId);
    }

    /**
     * @notice Called by the defaulter to make a partial payment into escrow.
     * This is now a monitored transfer.
     */
    function makePayment(uint256 tokenId, uint256 amount) external {
        RepaymentPlan storage plan = repaymentPlans[tokenId];
        require(plan.status == PlanStatus.Active, "Plan is not active");
        require(msg.sender == plan.defaulter, "Only the defaulter can make payments");
        require(plan.amountPaid + amount <= plan.totalOwed, "Payment exceeds amount owed");

        // Defaulter must have approved the CalculusEngine to spend their USDC
        calculusEngine.monitoredTransfer(plan.actionId, address(usdcToken), msg.sender, address(this), amount);
        
        plan.amountPaid += amount;
        emit PaymentMade(tokenId, amount);
    }

    /**
     * @notice Called once the full debt has been paid into escrow.
     * This atomically settles the debt.
     */
    function finalizePlan(uint256 tokenId) external {
        RepaymentPlan storage plan = repaymentPlans[tokenId];
        require(plan.status == PlanStatus.Active, "Plan is not active");
        require(plan.amountPaid == plan.totalOwed, "Debt not fully paid");

        plan.status = PlanStatus.Finalized;

        // 1. Pay the creditor via a monitored transfer from this contract.
        // This script must approve the engine to spend the funds it holds.
        usdcToken.approve(address(calculusEngine), plan.totalOwed);
        calculusEngine.monitoredTransfer(plan.actionId, address(usdcToken), address(this), plan.creditor, plan.totalOwed);

        // 2. Mark the master promise as fulfilled in the engine.
        calculusEngine.monitoredFulfillment(plan.masterPromiseId);

        // 3. Burn the RCT to unlock the defaulter's reputation.
        rctContract.burn(tokenId);

        emit PlanFinalized(tokenId);
    }

    // Note: A `cancelPlan` function would similarly need to use `monitoredTransfer`
    // to return the funds, and `monitoredDefault` to break the master promise.
}