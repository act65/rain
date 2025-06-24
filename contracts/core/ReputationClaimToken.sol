// File: contracts/ReputationClaimToken.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title ReputationClaimToken
 * @author Rain Protocol
 * @dev An ERC721 token where each token represents a unique, verifiable claim on a debt
 * from a defaulted loan. This token securitizes the debt, making it a tradable asset.
 */
contract ReputationClaimToken is ERC721, AccessControl {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    // Roles for controlling minting and burning
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    // Struct to hold the details of each debt claim
    struct DebtClaim {
        address defaulterAddress;
        address originalLenderAddress;
        uint256 shortfallAmount; // In USDC smallest unit
        uint256 defaultTimestamp;
        address loanContractAddress; // The Arbiter that witnessed the default
    }

    // Mapping from a token ID to its associated debt details
    mapping(uint256 => DebtClaim) public claims;

    event ClaimMinted(
        uint256 indexed tokenId,
        address indexed defaulter,
        address indexed originalLender,
        uint256 shortfallAmount
    );

    event ClaimBurned(uint256 indexed tokenId, address indexed burner);

    constructor() ERC721("Rain Reputation Claim", "RCT") {
        // Grant the contract deployer the default admin role, which can grant other roles
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    /**
     * @notice Mints a new Reputation Claim Token.
     * @dev Can only be called by a trusted contract with MINTER_ROLE (e.g., a LoanContract).
     * The token is assigned to the original lender.
     * @param defaulter The address of the user who defaulted.
     * @param originalLender The address of the lender who is owed the debt.
     * @param shortfallAmount The amount of the debt in USDC smallest unit.
     */
    function mint(
        address defaulter,
        address originalLender,
        uint256 shortfallAmount,
        address loanContract
    ) external returns (uint256) {
        require(hasRole(MINTER_ROLE, msg.sender), "RCT: Caller is not a minter");

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
     * @notice Burns a token after the debt has been settled.
     * @dev Can only be called by a trusted contract with BURNER_ROLE (e.g., the InsuranceFund
     * or a future repayment contract).
     * @param tokenId The ID of the token to burn.
     */
    function burn(uint256 tokenId) external {
        require(hasRole(BURNER_ROLE, msg.sender), "RCT: Caller is not a burner");
        
        // Clear the associated claim data to save gas (refund)
        delete claims[tokenId];
        _burn(tokenId);

        emit ClaimBurned(tokenId, msg.sender);
    }

    /**
     * @dev Required override for OpenZeppelin's AccessControl contract.
     */
    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}