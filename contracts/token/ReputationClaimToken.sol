// File: contracts/token/ReputationClaimToken.sol (Final, Secure Version)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

// Interface for the RainReputation contract
interface IRainReputation {
    function setDelinquentStatus(address user, bool status) external;
}

/**
 * @title ReputationClaimToken
 * @author Rain Protocol
 * @dev An ERC721 token representing a debt claim. This contract is now also responsible
 * for triggering the "Hard Lock" on the RainReputation contract when a user's
 * outstanding debt count changes from 0 to 1 (on mint) or 1 to 0 (on burn).
 */
contract ReputationClaimToken is ERC721, AccessControl {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    IRainReputation public immutable rainReputation;

    // --- NEW: State variable to track outstanding debts per user ---
    mapping(address => uint256) public debtCount;

    struct DebtClaim {
        address defaulterAddress;
        address originalLenderAddress;
        uint256 shortfallAmount;
        uint256 defaultTimestamp;
        address loanContractAddress;
    }
    mapping(uint256 => DebtClaim) public claims;

    event ClaimMinted(uint256 indexed tokenId, address indexed defaulter, address indexed originalLender, uint256 shortfallAmount);
    event ClaimBurned(uint256 indexed tokenId, address indexed burner);

    constructor(address _rainReputationAddress) ERC721("Rain Reputation Claim", "RCT") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        rainReputation = IRainReputation(_rainReputationAddress);
    }

    /**
     * @notice Mints a new RCT. If this is the user's first outstanding debt,
     * it atomically sets their status to delinquent.
     */
    function mint(
        address defaulter,
        address originalLender,
        uint256 shortfallAmount,
        address loanContract
    ) external returns (uint256) {
        require(hasRole(MINTER_ROLE, msg.sender), "RCT: Caller is not a minter");

        // --- REVISED LOGIC: Lock on first offense ---
        if (debtCount[defaulter] == 0) {
            rainReputation.setDelinquentStatus(defaulter, true);
        }
        debtCount[defaulter]++;

        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();

        claims[newItemId] = DebtClaim({
            defaulterAddress: defaulter,
            originalLenderAddress: originalLender,
            shortfallAmount: shortfallAmount,
            defaultTimestamp: block.timestamp,
            loanContractAddress: loanContract
        });

        _safeMint(originalLender, newItemId);
        emit ClaimMinted(newItemId, defaulter, originalLender, shortfallAmount);
        return newItemId;
    }

    /**
     * @notice Burns an RCT. If this is the user's last outstanding debt,
     * it atomically clears their delinquent status.
     */
    function burn(uint256 tokenId) external {
        require(hasRole(BURNER_ROLE, msg.sender), "RCT: Caller is not a burner");
        
        address defaulter = claims[tokenId].defaulterAddress;
        require(debtCount[defaulter] > 0, "Cannot decrement debt count below zero");
        
        delete claims[tokenId];
        _burn(tokenId);

        // --- REVISED LOGIC: Unlock when debt count reaches zero ---
        debtCount[defaulter]--;
        if (debtCount[defaulter] == 0) {
            rainReputation.setDelinquentStatus(defaulter, false);
        }

        emit ClaimBurned(tokenId, msg.sender);
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}