// File: contracts/ReputationSBT.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title ReputationSBT
 * @dev A non-transferable ERC721 token (Soulbound Token) used to represent
 * user identity and manage reputation scores.
 */
contract ReputationSBT is ERC721, Ownable {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    // Mapping from a user's address to their reputation score.
    mapping(address => uint256) public reputationScores;

    // Mapping from a user's address to their staked reputation amount.
    mapping(address => uint256) public stakedReputation;

    // Addresses of contracts that are allowed to modify reputation.
    mapping(address => bool) public isTrustedContract;

    constructor() ERC721("Reputation Token", "REPSBT") {}

    /**
     * @dev Mints a new SBT for a user and sets their initial reputation.
     * Can only be called by the contract owner (for initial user setup).
     */
    function mint(address user, uint256 initialReputation) public onlyOwner {
        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();
        _safeMint(user, newItemId);
        reputationScores[user] = initialReputation;
    }
    
    /**
     * @dev Adds a contract address to the list of trusted contracts that can
     * modify reputation scores (e.g., LoanContract, InsuranceDAO).
     */
    function setTrustedContract(address contractAddress, bool isTrusted) public onlyOwner {
        isTrustedContract[contractAddress] = isTrusted;
    }

    // --- Reputation Management (Called by Trusted Contracts) ---

    function increaseReputation(address user, uint256 amount) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        reputationScores[user] += amount;
    }

    function decreaseReputation(address user, uint256 amount) external {
        require(isTrustedContract[msg.sender], "Caller is not a trusted contract");
        if (reputationScores[user] >= amount) {
            reputationScores[user] -= amount;
        } else {
            reputationScores[user] = 0;
        }
    }

    // --- Staking and Slashing Logic (Called by Trusted Contracts) ---

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

    // --- Override transfer functions to make the token Soulbound ---

    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal virtual override {
        require(from == address(0), "SBT: This token is non-transferable");
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }
}