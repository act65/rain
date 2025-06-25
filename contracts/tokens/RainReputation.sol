// File: contracts/RainReputation.sol (Final Version)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title RainReputation
 * @author Rain Protocol
 * @dev The unified, definitive reputation contract. It acts as both the universal
 * Reputation Ledger and the stateful Staking Vault.
 */
contract RainReputation is ERC721, Ownable {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    // --- State Variables ---
    mapping(address => uint256) public reputationScores;
    mapping(address => uint256) public stakedReputation; // Total amount staked by a user
    mapping(address => bool) public isTrustedContract;
    mapping(address => bool) public isDelinquent;

    address public rctContractAddress;

    // Staking specific state
    struct Stake {
        address user;
        uint256 amount;
        bool isReleased;
    }
    // Mapping from a unique purposeId (e.g., a promiseId) to the stake that secures it
    mapping(bytes32 => Stake) public stakes;

    // --- Events ---
    event ReputationIncreased(address indexed user, uint256 amount, string reason);
    event ReputationDecreased(address indexed user, uint256 amount, string reason);
    event ReputationStaked(bytes32 indexed purposeId, address indexed user, uint256 amount);
    event StakeReleased(bytes32 indexed purposeId, address indexed user, uint256 amount);
    event ReputationSlashed(address indexed user, uint256 amount);
    event DelinquentStatusChanged(address indexed user, bool isDelinquent);

    constructor() ERC721("Rain Reputation Token", "RAIN") {}

    // --- SBT and Identity Management ---
    function mint(address user, uint256 initialReputation) public onlyOwner {
        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();
        _safeMint(user, newItemId);
        reputationScores[user] = initialReputation;
    }

    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal override {
        require(from == address(0), "RAIN: This token is non-transferable");
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }

    // --- Reputation & Staking Management (Called by Trusted Contracts) ---

    function increaseReputation(address user, uint256 amount, string calldata reason) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        
                // --- NEW: The Hard Lock Enforcement ---
        require(!isDelinquent[user], "RainReputation: User is delinquent and cannot earn reputation");
        
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

    /**
     * @notice Locks a user's reputation as collateral for a specific purpose.
     * @param user The user whose reputation is being staked.
     * @param amount The amount of reputation to lock.
     * @param purposeId A unique ID (e.g., promiseId from CalculusEngine) for the stake's purpose.
     */
    function stake(address user, uint256 amount, bytes32 purposeId) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        require(stakes[purposeId].amount == 0, "Stake for this purpose already exists");
        require(reputationScores[user] - stakedReputation[user] >= amount, "Insufficient liquid reputation");

        stakedReputation[user] += amount;
        stakes[purposeId] = Stake({
            user: user,
            amount: amount,
            isReleased: false
        });

        emit ReputationStaked(purposeId, user, amount);
    }

    /**
     * @notice Releases a user's staked reputation, making it liquid again.
     * @param purposeId The unique ID of the stake to release.
     */
    function releaseStake(bytes32 purposeId) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        Stake storage s = stakes[purposeId];
        require(s.amount > 0, "Stake does not exist");
        require(!s.isReleased, "Stake already released");

        s.isReleased = true;
        stakedReputation[s.user] -= s.amount;

        emit StakeReleased(purposeId, s.user, s.amount);
    }

    /**
     * @notice Slashes a user's reputation as a penalty.
     * @dev This is a destructive action that reduces both staked and total reputation.
     * It should be called after a default has been confirmed.
     */
    function slash(address user, uint256 amountToSlash) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        
        // Reduce the user's total score first
        if (reputationScores[user] >= amountToSlash) {
            reputationScores[user] -= amountToSlash;
        } else {
            reputationScores[user] = 0;
        }

        // Then reduce their staked amount
        if (stakedReputation[user] >= amountToSlash) {
            stakedReputation[user] -= amountToSlash;
        } else {
            stakedReputation[user] = 0;
        }

        emit ReputationSlashed(user, amountToSlash);
    }

    // --- Admin and View Functions ---
    function setTrustedContract(address contractAddress, bool isTrusted) public onlyOwner {
        isTrustedContract[contractAddress] = isTrusted;
    }

    function getLiquidReputation(address user) external view returns (uint256) {
        return reputationScores[user] - stakedReputation[user];
    }

    function setRctContract(address _rctContractAddress) external onlyOwner {
        require(rctContractAddress == address(0), "RCT contract already set");
        rctContractAddress = _rctContractAddress;
    }

    function setDelinquentStatus(address user, bool status) external {
        require(msg.sender == rctContractAddress, "Only the RCT contract can set delinquent status");
        isDelinquent[user] = status;
        emit DelinquentStatusChanged(user, status);
    }

}