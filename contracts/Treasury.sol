// File: contracts/Treasury.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./ReputationV2.sol"; // To get reputation scores for dividend calculation
import "./CurrencyToken.sol"; // The type of token for dividends (USDC)

/**
 * @title Treasury
 * @dev Manages system revenues and distributes dividends based on user reputation.
 */
contract Treasury is Ownable {
    ReputationV2 public reputationContract;
    CurrencyToken public usdcToken; // Using CurrencyToken as the dividend token (USDC)

    // Total dividends distributed over time
    uint256 public totalDividendsDistributed;

    // Placeholder for revenue collection. In a real system, other contracts would send fees here.
    // For now, the owner can deposit funds to be distributed as dividends.

    // For distributing dividends, iterating through all users with reputation is not scalable on-chain.
    // Common patterns are:
    // 1. Pull-based: Users claim their dividends. Requires users to be active.
    // 2. Snapshot-based with Merkle drops: Off-chain calculation of dividends, root hash on-chain. Users provide proof to claim.
    // 3. Simplified on-chain for small number of users (not suitable for production).

    // For this version, we'll implement a simplified pull-based system.
    // Users will "claim" their share of a dividend pool based on their reputation at the time of pool creation.
    // This requires creating "dividend cycles" or "pools".

    struct DividendCycle {
        uint256 id;
        uint256 totalDividendAmount; // Total USDC in this cycle's pool
        uint256 totalReputationSnapshot; // Total reputation points eligible at the start of cycle
        uint256 creationTimestamp;
        uint256 expiryTimestamp; // Optional: after which unclaimed funds might be rolled over
        mapping(address => uint256) claimedAmountByUser; // How much each user has claimed from this cycle
    }

    DividendCycle[] public dividendCycles;
    uint256 public currentDividendCycleId = 0; // Tracks the next ID to use

    // Minimum amount to start a new dividend cycle
    uint256 public minAmountForNewCycle;

    // Duration for which a dividend cycle is active for claims
    uint256 public claimPeriodDuration; // e.g., 30 days

    event RevenueReceived(address indexed from, uint256 amount);
    event DividendCycleCreated(uint256 indexed cycleId, uint256 totalAmount, uint256 totalReputationSnapshot);
    event DividendClaimed(uint256 indexed cycleId, address indexed user, uint256 amountClaimed, uint256 userReputation);

    constructor(
        address _reputationContractAddress,
        address _usdcTokenAddress,
        uint256 _minAmountForNewCycle,
        uint256 _claimPeriodDuration
    ) {
        require(_reputationContractAddress != address(0) && _usdcTokenAddress != address(0), "Contract addresses cannot be zero");
        require(_minAmountForNewCycle > 0, "Min amount for cycle must be positive");
        require(_claimPeriodDuration > 0, "Claim period duration must be positive");

        reputationContract = ReputationV2(_reputationContractAddress);
        usdcToken = CurrencyToken(_usdcTokenAddress); // Assuming CurrencyToken is our USDC
        minAmountForNewCycle = _minAmountForNewCycle;
        claimPeriodDuration = _claimPeriodDuration;
    }

    /**
     * @dev Allows the owner or other system contracts to send revenue (USDC) to the Treasury.
     * These funds will be used for future dividend cycles.
     */
    function depositRevenue(uint256 amount) external {
        // In a real system, this might be `payable` for ETH or require specific contract calls.
        // For USDC, it's a transfer.
        require(usdcToken.transferFrom(_msgSender(), address(this), amount), "USDC transfer for revenue failed");
        emit RevenueReceived(_msgSender(), amount);
    }

    /**
     * @dev Creates a new dividend cycle with the current available USDC balance in the Treasury
     * if it meets the minimum amount.
     * This function would typically be called periodically by an admin or an automated keeper.
     * For this version, it takes a snapshot of total reputation from users who have minted SBTs.
     * This is a simplification as ReputationV2 doesn't explicitly track all token holders for easy iteration.
     * A more robust system would require ReputationV2 to expose total circulating reputation or use off-chain snapshots.
     *
     * For now, let's assume `ReputationV2` has a way to get total reputation (e.g., a public variable `totalSystemReputation`).
     * This needs to be added to `ReputationV2` or this Treasury needs a list of users.
     *
     * Simplification: For now, `totalReputationSnapshot` will be manually provided or use a placeholder.
     * A better approach for on-chain is for users to register for a dividend cycle.
     *
     * Let's make `totalReputationSnapshot` a parameter for now, assuming it's calculated off-chain
     * or by a system admin who sums up all users' reputations.
     */
    function createDividendCycle(uint256 totalReputationSnapshotForCycle) external onlyOwner {
        // FUTURE WORK: Placeholder - `totalReputationSnapshotForCycle` is provided externally.
        // A more robust and decentralized system might:
        // 1. Have ReputationV2 maintain a running total of all active users' reputation scores.
        // 2. Use an off-chain snapshot mechanism (e.g., taken at a specific block number) where the
        //    list of users and their reputations is committed on-chain via a Merkle root.
        //    Claims would then require a Merkle proof.
        // 3. Implement a registration system where users actively register for a dividend cycle,
        //    allowing the contract to build the total reputation for that specific cycle.
        uint256 cycleAmount = usdcToken.balanceOf(address(this));

        require(cycleAmount >= minAmountForNewCycle, "Insufficient balance to start a new cycle meeting minimum");
        require(totalReputationSnapshotForCycle > 0, "Total reputation snapshot must be positive");

        currentDividendCycleId++;
        DividendCycle storage newCycle = dividendCycles.push();

        newCycle.id = currentDividendCycleId;
        newCycle.totalDividendAmount = cycleAmount;
        newCycle.totalReputationSnapshot = totalReputationSnapshotForCycle; // This is crucial
        newCycle.creationTimestamp = block.timestamp;
        newCycle.expiryTimestamp = block.timestamp + claimPeriodDuration;
        // `claimedAmountByUser` mapping is implicitly initialized.

        // Note: The USDC isn't "moved" here; it's just allocated from the Treasury's balance.
        // Claims will transfer it out.

        emit DividendCycleCreated(newCycle.id, newCycle.totalDividendAmount, newCycle.totalReputationSnapshot);
    }

    /**
     * @dev Allows a user to claim their dividend from a specific, active cycle.
     * Dividend for user = (UserReputationAtSnapshot / TotalReputationAtSnapshot) * TotalDividendAmountInCycle
     * User's reputation snapshot would ideally be part of the cycle data or provided via Merkle proof.
     * For on-chain simplicity here, we fetch current reputation. This is a known simplification/flaw
     * as reputation can change after cycle creation. A true snapshot system is more complex.
     *
     * To improve: `claimDividend` could take `userReputationAtSnapshot` as an argument,
     * validated by a signature from an oracle or admin if not using Merkle proofs.
     *
     * For this implementation, we will use the user's *current* reputation from ReputationV2.
     * This means users are incentivized to claim when their reputation is high relative to the snapshot total.
     */
    function claimDividend(uint256 cycleId) external {
        require(cycleId > 0 && cycleId <= dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[cycleId - 1]; // Adjust for 0-based array

        require(block.timestamp >= cycle.creationTimestamp, "Cycle not yet active (should not happen)");
        require(block.timestamp <= cycle.expiryTimestamp, "Dividend cycle has expired");
        require(cycle.totalDividendAmount > 0, "No dividends in this cycle"); // Should be caught by minAmountForNewCycle

        address claimant = _msgSender();
        uint256 alreadyClaimed = cycle.claimedAmountByUser[claimant];
        require(alreadyClaimed == 0, "Dividend already claimed by user for this cycle");

        // FUTURE WORK: Placeholder - User's reputation is fetched at the time of claim.
        // This means a user's dividend amount can change if their reputation changes after a cycle
        // is created but before they claim. A true snapshot system would use the user's reputation
        // *at the time the cycle was created/snapshotted*. This would typically involve:
        // - Storing each user's snapshot reputation (gas-intensive for many users).
        // - Or, more scalably, requiring users to provide a Merkle proof of their reputation at snapshot time,
        //   with the Merkle root being part of the DividendCycle data.
        uint256 userReputation = reputationContract.getEffectiveReputation(claimant);
        require(userReputation > 0, "User has no reputation, no dividend to claim");

        uint256 dividendAmount = (userReputation * cycle.totalDividendAmount) / cycle.totalReputationSnapshot;

        require(dividendAmount > 0, "Calculated dividend is zero (e.g., due to low reputation or rounding)");

        // FUTURE WORK: Placeholder - Pool Depletion Risk.
        // If `totalReputationSnapshotForCycle` is an underestimation or if many users' reputations increase
        // significantly before they claim, the sum of all potential claims might exceed `cycle.totalDividendAmount`.
        // A robust system would ensure that `cycle.totalDividendAmount` is precisely allocated or that
        // claims are pro-rated if the pool is about to be depleted.
        // The current `usdcToken.balanceOf(address(this)) >= dividendAmount` check offers some protection
        // but doesn't guarantee fairness for the last claimants if the sum of calculated shares is too high.
        require(usdcToken.balanceOf(address(this)) >= dividendAmount, "Treasury insufficient balance for this claim");

        cycle.claimedAmountByUser[claimant] = dividendAmount;
        totalDividendsDistributed += dividendAmount;

        require(usdcToken.transfer(claimant, dividendAmount), "USDC transfer for dividend failed");

        emit DividendClaimed(cycleId, claimant, dividendAmount, userReputation);
    }

    // --- View Functions ---

    function getDividendCycleDetails(uint256 cycleId) external view returns (
        uint256 id,
        uint256 totalAmount,
        uint256 totalReputationSnap,
        uint256 created,
        uint256 expires,
        uint256 claimedByCaller
    ) {
        require(cycleId > 0 && cycleId <= dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[cycleId - 1];
        return (
            cycle.id,
            cycle.totalDividendAmount,
            cycle.totalReputationSnapshot,
            cycle.creationTimestamp,
            cycle.expiryTimestamp,
            cycle.claimedAmountByUser[_msgSender()]
        );
    }

    function getNumberOfDividendCycles() external view returns (uint256) {
        return dividendCycles.length;
    }

    // --- Admin Functions ---
    function setMinAmountForNewCycle(uint256 _newMinAmount) public onlyOwner {
        require(_newMinAmount > 0, "Min amount must be positive");
        minAmountForNewCycle = _newMinAmount;
    }

    function setClaimPeriodDuration(uint256 _newDuration) public onlyOwner {
        require(_newDuration > 0, "Claim period duration must be positive");
        claimPeriodDuration = _newDuration;
    }

    // In a real scenario, a function to recover funds from expired cycles might be needed.
    // Or a way for the Treasury to use its own balance for operational costs if designed so.
    // FUTURE WORK: Implement a function `recoverFundsFromExpiredCycle(uint256 cycleId)`
    // that allows the owner to move unclaimed USDC from an expired cycle back to the Treasury's
    // general fund, making it available for future dividend cycles or other Treasury purposes.
    // This would require tracking how much was actually paid out from a cycle versus its initial totalDividendAmount.
}
