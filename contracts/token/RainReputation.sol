// File: contracts/token/RainReputation.sol (Final Version)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title RainReputation
 * @author Rain Protocol
 * @dev The unified, definitive reputation contract. It acts as both the universal
 * Reputation Ledger and the stateful Staking Vault.
 *
 * ARCHITECTURAL NOTE: This contract has been updated for the Atomic Action Framework.
 * The responsibility for gating actions has shifted.
 * 1. Staking (`stake`, `releaseStake`) is now permissionless. Any contract can call these
 *    functions. Security is no longer based on *who* calls the function, but on the
 *    verifiable economic context created by the CalculusEngine and the logic of the
 *    calling script.
 * 2. Reputation modification (`increaseReputation`, `decreaseReputation`, `slash`) is
 *    a destructive and privileged action. It is gated by an `UPDATER_ROLE`, which
 *    is granted exclusively to the trusted ReputationUpdater contract that acts on
 *    behalf of the off-chain oracle.
 */
contract RainReputation is ERC721, AccessControl {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    // --- Roles ---
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    // --- State Variables ---
    mapping(address => uint256) public reputationScores;
    mapping(address => uint256) public stakedReputation; // Total amount staked by a user
    mapping(address => bool) public isDelinquent;

    address public rctContractAddress;

    // Staking specific state
    struct Stake {
        address user;
        uint256 amount;
        bool isReleased;
    }
    // Mapping from a unique purposeId (e.g., a promiseId from CalculusEngine) to the stake that secures it
    mapping(bytes32 => Stake) public stakes;

    // --- Events ---
    event ReputationIncreased(address indexed user, uint256 amount, string reason);
    event ReputationDecreased(address indexed user, uint256 amount, string reason);
    event ReputationStaked(bytes32 indexed purposeId, address indexed user, uint256 amount);
    event StakeReleased(bytes32 indexed purposeId, address indexed user, uint256 amount);
    event ReputationSlashed(address indexed user, uint256 amount);
    event DelinquentStatusChanged(address indexed user, bool isDelinquent);

    constructor() ERC721("Rain Reputation Token", "RAIN") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    // --- SBT and Identity Management ---
    function mint(address user, uint256 initialReputation) public {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();
        _safeMint(user, newItemId);
        reputationScores[user] = initialReputation;
    }

    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal override {
        require(from == address(0), "RAIN: This token is non-transferable");
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }

    // --- Reputation Modification (Called by Trusted Updater) ---

    function increaseReputation(address user, uint256 amount, string calldata reason) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        require(!isDelinquent[user], "RainReputation: User is delinquent and cannot earn reputation");
        
        reputationScores[user] += amount;
        emit ReputationIncreased(user, amount, reason);
    }

    function decreaseReputation(address user, uint256 amount, string calldata reason) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        if (reputationScores[user] >= amount) {
            reputationScores[user] -= amount;
        } else {
            reputationScores[user] = 0;
        }
        emit ReputationDecreased(user, amount, reason);
    }

    function slash(address user, uint256 amountToSlash) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        
        if (reputationScores[user] >= amountToSlash) {
            reputationScores[user] -= amountToSlash;
        } else {
            reputationScores[user] = 0;
        }

        if (stakedReputation[user] >= amountToSlash) {
            stakedReputation[user] -= amountToSlash;
        } else {
            stakedReputation[user] = 0;
        }

        emit ReputationSlashed(user, amountToSlash);
    }

    // --- Permissionless Staking Management ---

    /**
     * @notice Locks a user's reputation as collateral for a specific purpose.
     * @dev This function is now permissionless and can be called by any contract.
     * @param user The user whose reputation is being staked.
     * @param amount The amount of reputation to lock.
     * @param purposeId A unique ID (e.g., promiseId from CalculusEngine) for the stake's purpose.
     */
    function stake(address user, uint256 amount, bytes32 purposeId) external {
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
     * @dev This function is now permissionless and can be called by any contract.
     * @param purposeId The unique ID of the stake to release.
     */
    function releaseStake(bytes32 purposeId) external {
        Stake storage s = stakes[purposeId];
        require(s.amount > 0, "Stake does not exist");
        require(!s.isReleased, "Stake already released");

        s.isReleased = true;
        stakedReputation[s.user] -= s.amount;

        emit StakeReleased(purposeId, s.user, s.amount);
    }

    // --- Delinquency and Admin Functions ---

    function setRctContract(address _rctContractAddress) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(rctContractAddress == address(0), "RCT contract already set");
        rctContractAddress = _rctContractAddress;
    }

    function setDelinquentStatus(address user, bool status) external {
        require(msg.sender == rctContractAddress, "Only the RCT contract can set delinquent status");
        isDelinquent[user] = status;
        emit DelinquentStatusChanged(user, status);
    }

    // --- View Functions ---
    function getLiquidReputation(address user) public view returns (uint256) {
        return reputationScores[user] - stakedReputation[user];
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}