// File: contracts/primitives/Treasury.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/// @dev The rate at which reputation fades (implemented by RainReputation).
interface IDecaySchedule {
    function decayPeriod() external view returns (uint256);
    function retentionPerPeriod() external view returns (uint256);
}

/**
 * @title Treasury
 * @author Rain Protocol
 * @dev Collects protocol fees and pays them out to reputation holders as a
 * "Reputation Dividend" via Merkle drops. It does not invest.
 *
 * Fees are paid out gradually. Everything the Treasury receives goes into the payout
 * fund, and each dividend cycle shares out a fixed fraction of the fund
 * (`releasePerCycle`). In steady state that is exactly what comes in. When fee income
 * changes, dividends follow it at the release rate instead of jumping.
 *
 * The release rate is the rate at which reputation decays, with one cycle per decay
 * period. Both are read from the reputation contract at deployment and cannot be
 * changed. Fees then enter the fund at the point price per point of reputation issued,
 * and the fund and the supply of reputation shrink at the same rate, so every point is
 * backed by its price in the fund whatever anyone else does: a point is never worth
 * more than it cost, at start-up, after a surge, or to someone who generates most of
 * the promises. (See experiments/surge_fixes.)
 *
 * Money in the Treasury is in exactly one of three places:
 *   - reserved for a dividend cycle: promised to holders until claimed, or until the
 *     cycle expires and is recovered;
 *   - the payout fund;
 *   - received but not yet counted (fees since the last cycle, recovered funds): this
 *     joins the fund when the next cycle starts.
 */
contract Treasury is AccessControl, ReentrancyGuard {

    bytes32 public constant MANAGER_ROLE = keccak256("MANAGER_ROLE");
    uint256 private constant ONE = 1e18;

    IERC20 public immutable usdcToken;
    uint256 public claimPeriodDuration;

    uint256 public reservedForDividends; // unclaimed funds of dividend cycles that have not been recovered
    uint256 public payoutFund;
    address public immutable decaySchedule; // the reputation contract
    uint256 public immutable releasePerCycle; // fraction of the fund shared out by each cycle, scaled by 1e18
    uint256 public immutable cycleInterval; // least time between two cycles, in seconds
    uint256 public lastCycleTimestamp;

    struct DividendCycle {
        uint256 id;
        bytes32 merkleRoot;
        uint256 totalAmount;
        uint256 claimedAmount;
        uint256 creationTimestamp;
        uint256 expiryTimestamp;
        mapping(address => bool) hasClaimed;
    }
    DividendCycle[] public dividendCycles;

    event DividendCycleCreated(uint256 indexed cycleId, bytes32 indexed merkleRoot, uint256 totalAmount);
    event PayoutFundChanged(uint256 indexed cycleId, uint256 received, uint256 paidOut, uint256 payoutFund);
    event DividendClaimed(uint256 indexed cycleId, address indexed user, uint256 amountClaimed);
    event FundsRecovered(uint256 indexed cycleId, uint256 amountRecovered);
    event ClaimPeriodUpdated(uint256 newDuration);

    /**
     * @param _decaySchedule The reputation contract. Each cycle shares out the fraction of
     * the fund that reputation loses per decay period, and cycles are one decay period apart.
     * Reputation that never decays would never be paid, so that is refused.
     */
    constructor(address _usdcTokenAddress, uint256 _initialClaimPeriodDuration, address _decaySchedule) {
        require(_usdcTokenAddress != address(0), "USDC token address cannot be zero");
        require(_decaySchedule != address(0), "Decay schedule address cannot be zero");
        uint256 retention = IDecaySchedule(_decaySchedule).retentionPerPeriod();
        require(retention < ONE, "Reputation must decay for fees to be paid out");
        usdcToken = IERC20(_usdcTokenAddress);
        claimPeriodDuration = _initialClaimPeriodDuration;
        decaySchedule = _decaySchedule;
        releasePerCycle = ONE - retention;
        cycleInterval = IDecaySchedule(_decaySchedule).decayPeriod();
        lastCycleTimestamp = block.timestamp;

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MANAGER_ROLE, msg.sender);
    }

    // --- Accounting views ---

    /// @notice Money received that the fund has not yet counted (it will at the next cycle).
    function uncounted() public view returns (uint256) {
        uint256 balance = usdcToken.balanceOf(address(this));
        uint256 assigned = reservedForDividends + payoutFund;
        return balance > assigned ? balance - assigned : 0;
    }

    /// @notice The pool the next dividend cycle shares out.
    function distributable() public view returns (uint256) {
        return ((payoutFund + uncounted()) * releasePerCycle) / ONE;
    }

    /// @notice The earliest time at which the next cycle can start.
    function nextCycleTimestamp() public view returns (uint256) {
        return lastCycleTimestamp + cycleInterval;
    }

    // --- Core Dividend Logic (MANAGER ONLY) ---

    /**
     * @notice Starts a dividend cycle over `distributable()`.
     * @param _merkleRoot Root of the (account, amount) leaves holders can claim.
     * @param _totalAmount Sum of those leaves. At most `distributable()`; whatever is not
     * shared out (rounding dust) stays in the fund.
     */
    function createDividendCycle(bytes32 _merkleRoot, uint256 _totalAmount) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(block.timestamp >= nextCycleTimestamp(), "Too soon for the next cycle");
        require(_totalAmount > 0, "Total dividend amount must be positive");

        uint256 received = uncounted();
        uint256 fund = payoutFund + received;
        require(_totalAmount <= (fund * releasePerCycle) / ONE, "Exceeds this cycle's release");

        uint256 cycleId = dividendCycles.length;
        dividendCycles.push();
        DividendCycle storage cycle = dividendCycles[cycleId];

        cycle.id = cycleId;
        cycle.merkleRoot = _merkleRoot;
        cycle.totalAmount = _totalAmount;
        cycle.creationTimestamp = block.timestamp;
        cycle.expiryTimestamp = block.timestamp + claimPeriodDuration;

        payoutFund = fund - _totalAmount;
        reservedForDividends += _totalAmount;
        lastCycleTimestamp = block.timestamp;

        emit DividendCycleCreated(cycleId, _merkleRoot, _totalAmount);
        emit PayoutFundChanged(cycleId, received, _totalAmount, payoutFund);
    }

    /// @notice After a cycle expires, returns what nobody claimed to the payout fund (at the next cycle).
    function recoverUnclaimedFunds(uint256 _cycleId) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];
        require(block.timestamp > cycle.expiryTimestamp, "Cannot recover funds from an active cycle");

        uint256 unclaimedAmount = cycle.totalAmount - cycle.claimedAmount;
        if (unclaimedAmount > 0) {
            cycle.claimedAmount = cycle.totalAmount; // Mark as fully "claimed" to balance books
            reservedForDividends -= unclaimedAmount;
            emit FundsRecovered(_cycleId, unclaimedAmount);
        }
    }

    // --- Public Dividend Claiming ---

    function claimDividend(uint256 _cycleId, uint256 _amount, bytes32[] calldata _merkleProof) external nonReentrant {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];

        require(block.timestamp <= cycle.expiryTimestamp, "Dividend cycle has expired");
        require(!cycle.hasClaimed[msg.sender], "Dividend already claimed for this cycle");

        bytes32 leaf = keccak256(abi.encodePacked(msg.sender, _amount));
        require(MerkleProof.verify(_merkleProof, cycle.merkleRoot, leaf), "Invalid Merkle proof");

        // The leaves of a cycle can never pay out more than the cycle reserved.
        require(cycle.claimedAmount + _amount <= cycle.totalAmount, "Claim exceeds cycle total");

        cycle.hasClaimed[msg.sender] = true;
        cycle.claimedAmount += _amount;
        reservedForDividends -= _amount;

        require(usdcToken.transfer(msg.sender, _amount), "USDC transfer failed");

        emit DividendClaimed(_cycleId, msg.sender, _amount);
    }

    // --- Admin ---

    function setClaimPeriodDuration(uint256 _newDuration) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(_newDuration > 0, "Claim period must be positive");
        claimPeriodDuration = _newDuration;
        emit ClaimPeriodUpdated(_newDuration);
    }

    // --- Getters ---

    function getCycleDetails(uint256 _cycleId)
        external
        view
        returns (
            uint256 id,
            bytes32 merkleRoot,
            uint256 totalAmount,
            uint256 claimedAmount,
            uint256 creationTimestamp,
            uint256 expiryTimestamp
        )
    {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];
        return (
            cycle.id,
            cycle.merkleRoot,
            cycle.totalAmount,
            cycle.claimedAmount,
            cycle.creationTimestamp,
            cycle.expiryTimestamp
        );
    }

    function hasUserClaimed(uint256 _cycleId, address _user) external view returns (bool) {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        return dividendCycles[_cycleId].hasClaimed[_user];
    }

    function getNumberOfCycles() external view returns (uint256) {
        return dividendCycles.length;
    }
}
