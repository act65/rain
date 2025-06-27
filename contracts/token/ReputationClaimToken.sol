// File: contracts/token/ReputationClaimToken.sol (Final, Secure Version with Default Resolution)
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
 * @dev An ERC721 token representing a debt claim. This version has been updated to
 * support the full default resolution lifecycle.
 *
 * Key Changes:
 * 1. The `mint` function now stores the `promiseId` of the broken promise, creating a
 *    permanent on-chain link between the debt and its origin.
 * 2. The `burn` function is now permissionless (`public`), allowing the token owner
 *    (e.g., a defaulter who has settled their debt) to burn it directly, which is
 *    essential for reclaiming their staked reputation via a script like LoanScript.
 */
contract ReputationClaimToken is ERC721, AccessControl {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    // BURNER_ROLE is no longer needed as burn is now permissionless for the token owner.

    IRainReputation public immutable rainReputation;

    // State variable to track outstanding debts per user
    mapping(address => uint256) public debtCount;

    // Updated struct to include the originating promiseId
    struct DebtClaim {
        uint256 promiseId;
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
     * @notice Mints a new RCT, linking it to the specific promise that was defaulted on.
     * @dev If this is the user's first outstanding debt, it atomically sets their status to delinquent.
     * @param promiseId The ID of the promise from the CalculusEngine that was broken.
     * @param defaulter The address of the user who broke the promise.
     * @param originalLender The address of the user to whom the promise was made.
     * @param shortfallAmount The value of the default.
     * @param loanContract The address of the script that witnessed the default.
     * @return The ID of the newly minted RCT.
     */
    function mint(
        uint256 promiseId,
        address defaulter,
        address originalLender,
        uint256 shortfallAmount,
        address loanContract
    ) external returns (uint256) {
        require(hasRole(MINTER_ROLE, msg.sender), "RCT: Caller is not a minter");

        // Lock on first offense
        if (debtCount[defaulter] == 0) {
            rainReputation.setDelinquentStatus(defaulter, true);
        }
        debtCount[defaulter]++;

        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();

        claims[newItemId] = DebtClaim({
            promiseId: promiseId,
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
    * @notice Burns an RCT. Can only be called by the owner of the token.
    * @dev This is a critical step in the debt resolution process. A defaulter must
    * re-acquire their RCT and call this function to clear their name. If this is
    * their last outstanding debt, it atomically clears their delinquent status.
    * @param tokenId The ID of the token to burn.
    */
    function burn(uint256 tokenId) public virtual {
        // FIX: Explicitly check that the caller is the owner of the token.
        // The OpenZeppelin _burn function is internal and does not perform this check itself.
        require(ownerOf(tokenId) == msg.sender, "ERC721: caller is not token owner or approved");

        address defaulter = claims[tokenId].defaulterAddress;
        require(debtCount[defaulter] > 0, "Cannot decrement debt count below zero");

        // It's crucial to call _burn before updating state to prevent re-entrancy attacks.
        _burn(tokenId);
        delete claims[tokenId];

        // Unlock when debt count reaches zero
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