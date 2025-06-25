// File: contracts/primitives/TreasuryV2.sol (Upgraded)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

// --- INTERFACES ---

/**
 * @dev A generic interface for a yield-bearing protocol.
 * Assumes the protocol takes a base asset (like USDC) and allows depositing/withdrawing it.
 */
interface IYieldSource {
    function deposit(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);
}


/**
 * @title TreasuryV2
 * @author Rain Protocol
 * @dev This contract is the economic engine of the protocol. It collects fees,
 * invests them in whitelisted, yield-bearing protocols, and distributes the
 * generated yield back to users as a "Reputation Dividend" via Merkle drops.
 */
contract TreasuryV2 is AccessControl, ReentrancyGuard {

    // --- Roles ---
    bytes32 public constant MANAGER_ROLE = keccak256("MANAGER_ROLE");

    // --- State Variables ---

    IERC20 public immutable usdcToken;
    uint256 public claimPeriodDuration;

    // Capital Management
    mapping(address => bool) public isWhitelistedYieldSource;
    mapping(address => uint256) public investedAmounts; // Tracks amount invested in each source

    // Dividend Distribution
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


    // --- Events ---

    event YieldSourceWhitelisted(address indexed source);
    event YieldSourceRemoved(address indexed source);
    event CapitalInvested(address indexed source, uint256 amount);
    event CapitalDivested(address indexed source, uint256 amount);

    event DividendCycleCreated(uint256 indexed cycleId, bytes32 indexed merkleRoot, uint256 totalAmount);
    event DividendClaimed(uint256 indexed cycleId, address indexed user, uint256 amountClaimed);
    event FundsRecovered(uint256 indexed cycleId, uint256 amountRecovered);
    event ClaimPeriodUpdated(uint256 newDuration);


    // --- Constructor ---

    constructor(
        address _usdcTokenAddress,
        uint256 _initialClaimPeriodDuration
    ) {
        require(_usdcTokenAddress != address(0), "USDC token address cannot be zero");
        usdcToken = IERC20(_usdcTokenAddress);
        claimPeriodDuration = _initialClaimPeriodDuration;

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MANAGER_ROLE, msg.sender);
    }


    // --- Capital Management (MANAGER ONLY) ---

    function addYieldSource(address _source) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        isWhitelistedYieldSource[_source] = true;
        emit YieldSourceWhitelisted(_source);
    }

    function removeYieldSource(address _source) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(investedAmounts[_source] == 0, "Cannot remove source with active investment");
        isWhitelistedYieldSource[_source] = false;
        emit YieldSourceRemoved(_source);
    }

    function invest(address _yieldSource, uint256 _amount) external nonReentrant {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(isWhitelistedYieldSource[_yieldSource], "Source not whitelisted");
        require(usdcToken.balanceOf(address(this)) >= _amount, "Insufficient liquid USDC");

        investedAmounts[_yieldSource] += _amount;
        
        usdcToken.approve(_yieldSource, _amount);
        // Example for Aave V3 pool. The interface might need adjustment for other protocols.
        IYieldSource(_yieldSource).deposit(address(usdcToken), _amount, address(this), 0);

        emit CapitalInvested(_yieldSource, _amount);
    }

    function divest(address _yieldSource, uint256 _amount) external nonReentrant {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(investedAmounts[_yieldSource] >= _amount, "Cannot divest more than invested");

        investedAmounts[_yieldSource] -= _amount;
        
        // Example for Aave V3 pool.
        IYieldSource(_yieldSource).withdraw(address(usdcToken), _amount, address(this));

        emit CapitalDivested(_yieldSource, _amount);
    }


    // --- Core Dividend Logic (MANAGER ONLY) ---

    function createDividendCycle(bytes32 _merkleRoot, uint256 _totalAmount) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(_totalAmount > 0, "Total dividend amount must be positive");
        require(usdcToken.balanceOf(address(this)) >= _totalAmount, "Insufficient liquid Treasury balance for this cycle");

        uint256 cycleId = dividendCycles.length;
        dividendCycles.push(); // Creates empty element to avoid memory-to-storage copy issues
        DividendCycle storage cycle = dividendCycles[cycleId];

        cycle.id = cycleId;
        cycle.merkleRoot = _merkleRoot;
        cycle.totalAmount = _totalAmount;
        cycle.creationTimestamp = block.timestamp;
        cycle.expiryTimestamp = block.timestamp + claimPeriodDuration;

        emit DividendCycleCreated(cycleId, _merkleRoot, _totalAmount);
    }

    function recoverUnclaimedFunds(uint256 _cycleId) external {
        require(hasRole(MANAGER_ROLE, msg.sender), "Manager only");
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        DividendCycle storage cycle = dividendCycles[_cycleId];
        require(block.timestamp > cycle.expiryTimestamp, "Cannot recover funds from an active cycle");

        uint256 unclaimedAmount = cycle.totalAmount - cycle.claimedAmount;
        if (unclaimedAmount > 0) {
            cycle.claimedAmount = cycle.totalAmount; // Mark as fully "claimed" to balance books
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

        cycle.hasClaimed[msg.sender] = true;
        cycle.claimedAmount += _amount;

        require(usdcToken.transfer(msg.sender, _amount), "USDC transfer failed");

        emit DividendClaimed(_cycleId, msg.sender, _amount);
    }


    // --- Admin and View Functions ---

    function setClaimPeriodDuration(uint256 _newDuration) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(_newDuration > 0, "Claim period must be positive");
        claimPeriodDuration = _newDuration;
        emit ClaimPeriodUpdated(_newDuration);
    }

    function getTotalValue() external view returns (uint256) {
        // This is a simplified view. A production version would need to query each
        // yield source to get the current value including accrued interest.
        // For now, it shows the principal invested.
        uint256 totalInvested;
        // This loop would be too expensive on-chain if many sources are used.
        // This is better calculated off-chain. For on-chain, we just sum principals.
        // In a real scenario, you'd track yield-bearing tokens and their exchange rates.
        // For this version, we assume principal = value.
        // A more advanced version would require a more complex accounting system.
        return usdcToken.balanceOf(address(this)) + totalInvested; // Placeholder for invested value
    }

    function getCycleDetails(uint256 _cycleId) external view returns (DividendCycle memory) {
        require(_cycleId < dividendCycles.length, "Invalid cycle ID");
        return dividendCycles[_cycleId];
    }

    function getNumberOfCycles() external view returns (uint256) {
        return dividendCycles.length;
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}