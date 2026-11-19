// File: contracts/token/ReputationClaimToken.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

interface IRainReputation {
    function setDelinquentStatus(address user, bool status) external;
}

interface ICalculusEngineLog {
    function promises(uint256 promiseId) external view returns (uint256 actionId, address promisor, address promisee, address asset, uint256 amount, uint256 deadline, uint8 status, uint256 feePaid);
    function actions(uint256 actionId) external view returns (address user, address script);
}

/**
 * @title ReputationClaimToken
 * @author Rain Protocol
 * @dev An ERC721 token representing a claim on a defaulted promise.
 *
 * Minting needs no role. An RCT can only be minted for a promise that the
 * CalculusEngine records as Defaulted, only by the script that owns that promise,
 * and only once. Every field of the claim is read from the engine's log, so a
 * script cannot make an innocent user delinquent or overstate a debt.
 *
 * While a user has at least one outstanding RCT against them they are delinquent.
 */
contract ReputationClaimToken is ERC721 {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    uint8 private constant STATUS_DEFAULTED = 2; // CalculusEngine.PromiseStatus.Defaulted

    IRainReputation public immutable rainReputation;
    ICalculusEngineLog public immutable calculusEngine;

    // Outstanding debts per user
    mapping(address => uint256) public debtCount;

    struct DebtClaim {
        uint256 promiseId;
        address defaulterAddress;
        address originalLenderAddress;
        uint256 shortfallAmount;
        uint256 defaultTimestamp;
        address loanContractAddress;
    }
    mapping(uint256 => DebtClaim) public claims;
    // promiseId => the RCT minted for it (kept after the RCT is burned, so it cannot be minted twice)
    mapping(uint256 => uint256) public claimForPromise;

    event ClaimMinted(uint256 indexed tokenId, address indexed defaulter, address indexed originalLender, uint256 shortfallAmount);
    event ClaimBurned(uint256 indexed tokenId, address indexed burner);

    constructor(address _rainReputationAddress, address _calculusEngineAddress) ERC721("Rain Reputation Claim", "RCT") {
        rainReputation = IRainReputation(_rainReputationAddress);
        calculusEngine = ICalculusEngineLog(_calculusEngineAddress);
    }

    /**
     * @notice Mints the RCT for a defaulted promise to its promisee.
     * @dev If this is the promisor's first outstanding debt, it atomically marks them delinquent.
     * @param promiseId The defaulted promise in the CalculusEngine.
     * @return The ID of the newly minted RCT.
     */
    function mint(uint256 promiseId) external returns (uint256) {
        (uint256 actionId, address defaulter, address lender, , uint256 amount, , uint8 status, ) = calculusEngine.promises(promiseId);
        require(status == STATUS_DEFAULTED, "RCT: Promise is not defaulted");
        (, address script) = calculusEngine.actions(actionId);
        require(script == msg.sender, "RCT: Caller is not the script for this promise");
        require(claimForPromise[promiseId] == 0, "RCT: Claim already minted for this promise");

        if (debtCount[defaulter] == 0) {
            rainReputation.setDelinquentStatus(defaulter, true);
        }
        debtCount[defaulter]++;

        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();
        claimForPromise[promiseId] = newItemId;

        claims[newItemId] = DebtClaim({
            promiseId: promiseId,
            defaulterAddress: defaulter,
            originalLenderAddress: lender,
            shortfallAmount: amount,
            defaultTimestamp: block.timestamp,
            loanContractAddress: msg.sender
        });

        // _mint rather than _safeMint: a promisee that cannot receive NFTs must not block the default.
        _mint(lender, newItemId);
        emit ClaimMinted(newItemId, defaulter, lender, amount);
        return newItemId;
    }

    /**
    * @notice Burns an RCT. Can only be called by the owner of the token OR an approved address.
    * @dev Burning is the proof of settlement (or forgiveness). If this is the defaulter's
    * last outstanding debt, it atomically clears their delinquent status.
    */
    function burn(uint256 tokenId) public virtual {
        require(_isApprovedOrOwner(msg.sender, tokenId), "ERC721: burn caller is not owner nor approved");

        address defaulter = claims[tokenId].defaulterAddress;

        _burn(tokenId);
        delete claims[tokenId];

        debtCount[defaulter]--;
        if (debtCount[defaulter] == 0) {
            rainReputation.setDelinquentStatus(defaulter, false);
        }

        emit ClaimBurned(tokenId, msg.sender);
    }
}
