// File: contracts/token/RainReputation.sol (Final Version, Updated with Total Reputation Tracking)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title RainReputation
 * @author Rain Protocol
 * @dev The unified, definitive reputation contract. It acts as both the universal
 * Reputation Ledger and the stateful Staking Vault. It now also tracks the total
 * amount of reputation in the system to facilitate dynamic fee calculations.
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

    // --- NEW: Total reputation tracking for protocol-wide calculations ---
    uint256 public totalReputation;

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
        
        // --- MODIFIED: Update total reputation ---
        totalReputation += initialReputation;
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
        
        // --- MODIFIED: Update total reputation ---
        totalReputation += amount;

        emit ReputationIncreased(user, amount, reason);
    }


    /**
    * @notice Applies a routine, rule-based decrease to a user's reputation score.
    * @dev This function is intended to be called by the trusted oracle in response to
    * observable, predictable on-chain events, such as a `PromiseDefaulted` event from
    * the CalculusEngine. It emits a `ReputationDecreased` event.
    * @param user The address of the user.
    * @param amount The amount to decrease the score by.
    * @param reason A string detailing the specific on-chain event that triggered this decrease.
    */
    function decreaseReputation(address user, uint256 amount, string calldata reason) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        
        uint256 actualDecrease = reputationScores[user] >= amount ? amount : reputationScores[user];

        if (actualDecrease > 0) {
            reputationScores[user] -= actualDecrease;
            // --- MODIFIED: Update total reputation ---
            totalReputation -= actualDecrease;
        }

        emit ReputationDecreased(user, actualDecrease, reason);
    }

    /**
    * @notice Applies a severe, punitive penalty to a user's reputation score.
    * @dev This function signifies a more serious punishment than a routine decrease. It is
    * intended for use in response to extraordinary events, such as a governance vote or
    * a ruling from a future arbitration module. It emits a `ReputationSlashed` event,
    * signaling a higher level of risk to the ecosystem.
    * @param user The address of the user to be slashed.
    * @param amountToSlash The amount to slash the score by.
    */
    function slash(address user, uint256 amountToSlash) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");

        // --- REVISED LOGIC TO AVOID DOUBLE COUNTING ---
        uint256 currentScore = reputationScores[user];
        uint256 actualSlashAmount = currentScore > amountToSlash ? amountToSlash : currentScore;

        if (actualSlashAmount > 0) {
            reputationScores[user] -= actualSlashAmount;
            totalReputation -= actualSlashAmount; // Add this line
            emit ReputationSlashed(user, actualSlashAmount);
        }
        // Note: We no longer modify stakedReputation here as per our discussion.
    }

    // --- Permissionless Staking Management ---

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