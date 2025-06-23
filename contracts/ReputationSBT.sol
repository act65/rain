// File: contracts/Reputation.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title Reputation
 * @author Rain Protocol
 * @dev This is the unified, definitive reputation contract for the Rain ecosystem.
 * It combines three core functions into a single atomic unit:
 * 1.  Identity: A non-transferable ERC721 (Soulbound Token) represents each user's identity.
 * 2.  Staking: Users can stake their reputation score as collateral.
 * 3.  Economic Logic: Implements the "Fee-per-Action" model to generate protocol revenue.
 */
contract Reputation is ERC721, Ownable {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    // --- State Variables ---

    // Core Reputation Data
    mapping(address => uint256) public reputationScores;
    mapping(address => uint256) public stakedReputation;
    mapping(address => bool) public isTrustedContract;

    // Fee-per-Action ("Gas Tank") Model
    IERC20 public immutable usdcToken;
    address public immutable treasuryAddress;
    uint256 public actionFee;
    mapping(address => uint256) public actionNonces;


    // --- Events ---

    event ActionAuthorized(address indexed user, address indexed caller, uint256 nonce, bytes32 actionHash);
    event ReputationIncreased(address indexed user, uint256 amount, string reason);
    event ReputationDecreased(address indexed user, uint256 amount, string reason);
    event ActionFeeUpdated(uint256 newFee);


    // --- Constructor ---

    constructor(
        address _usdcTokenAddress,
        address _treasuryAddress,
        uint256 _initialActionFee
    ) ERC721("Rain Reputation Token", "RAIN") {
        require(_usdcTokenAddress != address(0), "USDC token address cannot be zero");
        require(_treasuryAddress != address(0), "Treasury address cannot be zero");

        usdcToken = IERC20(_usdcTokenAddress);
        treasuryAddress = _treasuryAddress;
        actionFee = _initialActionFee;
    }


    // --- SBT and Identity Management ---

    /**
     * @notice Mints a new Soulbound Token for a user and sets their initial reputation.
     * @dev Can only be called by the contract owner (for initial user setup).
     */
    function mint(address user, uint256 initialReputation) public onlyOwner {
        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();
        _safeMint(user, newItemId);
        reputationScores[user] = initialReputation;
    }

    /**
     * @dev Makes the ERC721 token non-transferable (Soulbound).
     */
    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal override {
        require(from == address(0), "RAIN: This token is non-transferable");
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }


    // --- Core Economic Logic (Fee-per-Action) ---

    /**
     * @notice Authorizes a single, reputation-backed action and charges a fee.
     * @dev The user must have pre-approved this contract to spend the `actionFee` amount of USDC.
     * @param user The address of the end-user whose reputation is being checked.
     * @param requiredReputation The minimum reputation score needed to perform the action.
     * @return actionHash A unique hash that the calling contract can use as a single-use authorization.
     */
    function authorizeAction(address user, uint256 requiredReputation) external returns (bytes32) {
        require(isTrustedContract[msg.sender], "Caller is not a trusted system contract");
        require(reputationScores[user] >= requiredReputation, "Insufficient reputation for action");

        if (actionFee > 0) {
            require(usdcToken.transferFrom(user, treasuryAddress, actionFee), "Action fee transfer failed");
        }

        uint256 nonce = actionNonces[user];
        bytes32 actionHash = keccak256(abi.encodePacked(user, msg.sender, nonce));
        actionNonces[user]++;

        emit ActionAuthorized(user, msg.sender, nonce, actionHash);
        return actionHash;
    }


    // --- Reputation & Staking Management (Called by Trusted Contracts) ---

    function increaseReputation(address user, uint256 amount, string calldata reason) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        reputationScores[user] += amount;
        emit ReputationIncreased(user, amount, reason);
    }

    function decreaseReputation(address user, uint256 amount, string calldata reason) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        if (reputationScores[user] >= amount) {
            reputationScores[user] -= amount;
        } else {
            reputationScores[user] = 0;
        }
        emit ReputationDecreased(user, amount, reason);
    }

    function stake(address user, uint256 amount) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        require(reputationScores[user] >= stakedReputation[user] + amount, "Insufficient reputation to stake");
        stakedReputation[user] += amount;
    }

    function releaseStake(address user, uint256 amount) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        require(stakedReputation[user] >= amount, "Cannot release more than staked");
        stakedReputation[user] -= amount;
    }

    function slash(address user, uint256 amount) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        require(stakedReputation[user] >= amount, "Cannot slash more than staked");
        
        stakedReputation[user] -= amount;
        
        if (reputationScores[user] >= amount) {
            reputationScores[user] -= amount;
        } else {
            reputationScores[user] = 0;
        }
    }


    // --- Admin and View Functions ---

    function setTrustedContract(address contractAddress, bool isTrusted) public onlyOwner {
        isTrustedContract[contractAddress] = isTrusted;
    }

    function setActionFee(uint256 _newFee) external onlyOwner {
        actionFee = _newFee;
        emit ActionFeeUpdated(_newFee);
    }

    function getReputation(address user) external view returns (uint256) {
        return reputationScores[user];
    }
}