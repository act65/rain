// File: contracts/Treasury.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/**
 * @title Treasury
 * @author Rain Protocol
 * @dev This contract manages the protocol's funds, collected from ecosystem fees.
 * It distributes yield generated from these funds back to users as a "Reputation Dividend"
 * using a gas-efficient and scalable Merkle drop mechanism.
 */
contract Treasury is Ownable {

    // --- State Variables ---

    IERC20 public immutable usdcToken;
    uint256 public claimPeriodDuration; // The duration for which a dividend cycle is active

    struct DividendCycle {
        uint256 id;
        bytes32 merkleRoot;             // The root of the distribution tree for this cycle
        uint256 totalAmount;            // Total USDC allocated to this cycle's pool
        uint256 claimedAmount;          // Total USDC claimed from this cycle so far
        uint256 creationTimestamp;
        uint256 expiryTimestamp;
        mapping(address => bool) hasClaimed; // Prevents a user from double-claiming in a cycle
    }

    DividendCycle[] public dividendCycles;


    // --- Events ---

    event DividendCycleCreated(uint256 indexed cycleId, bytes32 indexed merkleRoot, uint256 totalAmount);
    event DividendClaimed(uint256 indexed cycleId, address indexed user, uint256 amountClaimed);
    event FundsRecovered(uint256 indexed cycleId, uint256 amountRecovered);
    event ClaimPeriodUpdated(uint256 newDuration);


    // --- Constructor ---

    constructor(
        address _usdcTokenAddress,
        uint256 _initialClaimPeriodDuration // e.g., 30 days in seconds
    ) {
        require(_usdcTokenAddress != address(0), "USDC token address cannot be zero");
        usdcToken = IERC20(_usdcTokenAddress);
        claimPeriodDuration = _initialClaimPeriodDuration;
    }


    // --- Core Dividend Logic ---

    /**
     * @notice Creates a new dividend cycle for distribution.
     * @dev Can only be called by the owner (or a trusted keeper bot). The owner is responsible
     * for calculating the distribution off-chain, generating the Merkle tree, and ensuring
     * this contract has sufficient USDC balance to cover the total amount.
     * @param _merkleRoot The root hash of the Merkle tree containing all `(address, amount)` pairs.
     * @param _totalAmount The total amount of USDC being distributed in this cycle.
     */
    function createDividendCycle(bytes32 _merkleRoot, uint256 _totalAmount) external onlyOwner {
        require(_totalAmount > 0, "Total dividend amount must be positive");
        require(usdcToken.balanceOf(address(this)) >= _totalAmount, "Insufficient Treasury balance for this cycle");

        uint256 cycleId = dividendCycles.length;
        dividendCycles.push(DividendCycle({
            id: cycleId,
            merkleRoot: _merkleRoot,
            totalAmount: _totalAmount,
            claimedAmount: 0,
            creationTimestamp: block.timestamp,
            expiryTimestamp: block.timestamp + claimPeriodDuration,
        }));

        emit DividendCycleCreated(cycleId, _merkleRoot, _totalAmount);
    }

    /**
     * @notice Allows a user to claim their dividend from a specific, active cycle.
     * @dev The user must provide a Merkle proof generated off-chain that proves their
     * inclusion and dividend amount in the cycle's distribution.
     * @param _cycleId The ID of the dividend cycle to claim from.
     * @param _amount The amount of the dividend the user is claiming.
     * @param _merkleProof The proof of inclusion from the Merkle tree.
     */
    function claimDividend(uint256 _cycleId, uint256 _amount, bytes32[] calldata _merkleProof) external {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];

        require(block.timestamp <= cycle.expiryTimestamp, "Dividend cycle has expired");
        require(!cycle.hasClaimed[msg.sender], "Dividend already claimed for this cycle");

        // Verify the claim against the Merkle root stored for this cycle
        bytes32 leaf = keccak256(abi.encodePacked(msg.sender, _amount));
        require(MerkleProof.verify(_merkleProof, cycle.merkleRoot, leaf), "Invalid Merkle proof");

        // Mark as claimed to prevent double-spending
        cycle.hasClaimed[msg.sender] = true;
        cycle.claimedAmount += _amount;

        // Transfer the funds
        require(usdcToken.transfer(msg.sender, _amount), "USDC transfer failed");

        emit DividendClaimed(_cycleId, msg.sender, _amount);
    }


    // --- Admin Functions ---

    /**
     * @notice Recovers unclaimed funds from an expired dividend cycle.
     * @dev This allows for capital to be re-allocated to future dividend cycles.
     * Can only be called by the owner.
     * @param _cycleId The ID of the expired cycle to recover funds from.
     */
    function recoverUnclaimedFunds(uint256 _cycleId) external onlyOwner {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];

        require(block.timestamp > cycle.expiryTimestamp, "Cannot recover funds from an active cycle");

        uint256 unclaimedAmount = cycle.totalAmount - cycle.claimedAmount;
        
        if (unclaimedAmount > 0) {
            // To recover, we simply mark the full totalAmount as "claimed",
            // which effectively moves the unclaimed funds back into the Treasury's general pool
            // for the next dividend cycle. No transfer is needed as the funds are already here.
            cycle.claimedAmount = cycle.totalAmount;
            emit FundsRecovered(_cycleId, unclaimedAmount);
        }
    }

    /**
     * @notice Updates the duration for which dividend cycles are active.
     * @param _newDuration The new claim period in seconds.
     */
    function setClaimPeriodDuration(uint256 _newDuration) external onlyOwner {
        require(_newDuration > 0, "Claim period must be positive");
        claimPeriodDuration = _newDuration;
        emit ClaimPeriodUpdated(_newDuration);
    }


    // --- View Functions ---

    /**
     * @notice Gets the details for a specific dividend cycle.
     * @param _cycleId The ID of the cycle.
     * @return A memory object with the cycle's details.
     */
    function getCycleDetails(uint256 _cycleId) external view returns (DividendCycle memory) {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        return dividendCycles[_cycleId];
    }

    /**
     * @notice Gets the total number of dividend cycles created.
     * @return The number of cycles.
     */
    function getNumberOfCycles() external view returns (uint256) {
        return dividendCycles.length;
    }
}