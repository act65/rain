// File: contracts/scripts/PartialRepaymentEscrow.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/Counters.sol";

// --- INTERFACES FOR CORE PROTOCOL & TOKENS ---

interface ICalculusEngine {
    function monitoredAction(address user) external returns (uint256);
    function monitoredTransfer(uint256 actionId, address asset, address from, address to, uint256 amount) external;
}

interface IReputationClaimToken {
    function ownerOf(uint256 tokenId) external view returns (address);
    function burn(uint256 tokenId) external;
    function transferFrom(address from, address to, uint256 tokenId) external;
    function claims(uint256 tokenId) external view returns (address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/**
 * @title PartialRepaymentEscrow
 * @author Rain Protocol
 * @dev An example script demonstrating how to build a stateful escrow for settling
 * defaulted debt (represented by an RCT) via partial payments.
 *
 * ARCHITECTURAL NOTE: This contract's complexity highlights why a future
 * `conditionalTransfer` primitive in the CalculusEngine would be so powerful.
 * With that primitive, this entire stateful escrow could be replaced by a nearly
 * stateless script that simply sets up the conditions in the engine itself.
 */
contract PartialRepaymentEscrow {
    using Counters for Counters.Counter;
    Counters.Counter private _escrowIdCounter;

    // --- STATE ---

    ICalculusEngine public immutable calculusEngine;
    IReputationClaimToken public immutable rctContract;
    IERC20 public immutable usdcToken;

    enum Status { Active, Completed, Cancelled }

    struct Escrow {
        address rctHolder;
        address defaulter;
        uint256 rctId;
        uint256 totalToRepay;
        uint256 amountPaid;
        Status status;
    }

    mapping(uint256 => Escrow) public escrows;

    // --- EVENTS ---

    event EscrowCreated(uint256 indexed escrowId, uint256 indexed rctId, address indexed rctHolder, address defaulter, uint256 totalToRepay);
    event PaymentMade(uint256 indexed escrowId, uint256 amount);
    event EscrowCompleted(uint256 indexed escrowId);
    event EscrowCancelled(uint256 indexed escrowId);


    // --- SETUP ---

    constructor(
        address _calculusEngineAddress,
        address _rctContractAddress,
        address _usdcTokenAddress
    ) {
        calculusEngine = ICalculusEngine(_calculusEngineAddress);
        rctContract = IReputationClaimToken(_rctContractAddress);
        usdcToken = IERC20(_usdcTokenAddress);
    }

    // --- ESCROW LIFECYCLE ---

    /**
     * @notice The RCT holder initiates an escrow agreement.
     * @dev This locks the RCT in this contract, proving ownership and preventing its sale.
     * @param rctId The ID of the Reputation Claim Token representing the debt.
     * @param defaulter The address of the user who will be making payments.
     */
    function createEscrow(uint256 rctId, address defaulter) external {
        require(rctContract.ownerOf(rctId) == msg.sender, "Not the RCT owner");

        // The RCT holder must have approved this contract to transfer their RCT.
        rctContract.transferFrom(msg.sender, address(this), rctId);

        _escrowIdCounter.increment();
        uint256 escrowId = _escrowIdCounter.current();

        // Get the debt amount from the RCT contract's public data
        (,,,, uint256 shortfallAmount,,) = rctContract.claims(rctId);

        escrows[escrowId] = Escrow({
            rctHolder: msg.sender,
            defaulter: defaulter,
            rctId: rctId,
            totalToRepay: shortfallAmount,
            amountPaid: 0,
            status: Status.Active
        });

        emit EscrowCreated(escrowId, rctId, msg.sender, defaulter, shortfallAmount);
    }

    /**
     * @notice The defaulter makes a partial payment into the escrow.
     * @param escrowId The ID of the escrow agreement.
     * @param amount The amount of USDC to pay.
     */
    function makePayment(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.status == Status.Active, "Escrow not active");
        require(escrow.defaulter == msg.sender, "Not the designated defaulter");
        require(amount > 0, "Payment must be positive");

        // The defaulter must have approved this contract to spend their USDC.
        usdcToken.transferFrom(msg.sender, address(this), amount);
        escrow.amountPaid += amount;

        emit PaymentMade(escrowId, amount);

        // If the full amount has been paid, complete the escrow.
        if (escrow.amountPaid >= escrow.totalToRepay) {
            _completeEscrow(escrowId);
        }
    }

    /**
     * @notice Internal function to finalize the escrow once paid in full.
     */
    function _completeEscrow(uint256 escrowId) internal {
        Escrow storage escrow = escrows[escrowId];
        escrow.status = Status.Completed;

        // 1. Start a monitored action for the final settlement.
        uint256 actionId = calculusEngine.monitoredAction(address(this));

        // 2. Transfer the collected funds to the original RCT holder.
        calculusEngine.monitoredTransfer(actionId, address(usdcToken), address(this), escrow.rctHolder, escrow.totalToRepay);

        // 3. Burn the RCT to clear the defaulter's name.
        // IMPORTANT: This contract must be granted the BURNER_ROLE on the RCT contract.
        rctContract.burn(escrow.rctId);

        emit EscrowCompleted(escrowId);
    }

    /**
     * @notice Allows the RCT holder to cancel the agreement and retrieve their RCT
     * if the defaulter stops paying.
     * @param escrowId The ID of the escrow to cancel.
     */
    function cancelEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.status == Status.Active, "Escrow not active");
        require(escrow.rctHolder == msg.sender, "Not the RCT holder");

        escrow.status = Status.Cancelled;

        // Return any partial payments to the defaulter
        if (escrow.amountPaid > 0) {
            usdcToken.transfer(escrow.defaulter, escrow.amountPaid);
        }

        // Return the RCT to the holder
        rctContract.transferFrom(address(this), escrow.rctHolder, escrow.rctId);

        emit EscrowCancelled(escrowId);
    }
}