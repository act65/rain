// File: contracts/OfflineToken.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Context.sol";
import "./ReputationV2.sol"; // Using ReputationV2 for staking

/**
 * @title OfflineToken
 * @dev Manages staking of reputation for minting Offline Tokens (ERC1155).
 * Allows slashing of staked reputation by trusted authorities.
 */
contract OfflineToken is ERC1155, Ownable {
    ReputationV2 public reputationContract;

    // Define a specific ID for the Offline Tokens within the ERC1155 contract
    uint256 public constant OFFLINE_TOKEN_ID = 0;

    // Mapping from user address to the amount of reputation they have staked
    mapping(address => uint256) public stakedReputationByUser;

    // Total reputation staked in this contract
    uint256 public totalReputationStaked;

    // Conversion rate: 1 unit of reputation = X Offline Tokens
    // FUTURE WORK: Placeholder - The REPUTATION_TO_TOKEN_RATIO is constant.
    // A more dynamic system might adjust this ratio based on factors like:
    // - The user's overall reputation score (higher reputation = better ratio).
    // - System-wide risk assessment.
    // - Governance decisions.
    uint256 public constant REPUTATION_TO_TOKEN_RATIO = 1;

    // Address of the Jury contract (or other trusted authority) allowed to slash stakes
    address public juryContractAddress;

    event ReputationStaked(address indexed user, uint256 reputationAmount, uint256 tokenAmountMinted);
    event StakeReleased(address indexed user, uint256 reputationAmountReleased, uint256 tokenAmountBurned);
    event StakeSlashed(address indexed user, uint256 reputationAmountSlashed, uint256 tokenAmountBurned);

    constructor(address _reputationContractAddress) ERC1155("") { // URI can be set later if needed
        require(_reputationContractAddress != address(0), "Reputation contract address cannot be zero");
        reputationContract = ReputationV2(_reputationContractAddress);
    }

    /**
     * @dev Sets the address of the Jury contract, which is authorized to slash stakes.
     * Can only be called by the contract owner.
     */
    function setJuryContract(address _juryAddress) public onlyOwner {
        require(_juryAddress != address(0), "Jury address cannot be zero");
        juryContractAddress = _juryAddress;
    }

    /**
     * @dev Allows a user to stake their reputation to mint Offline Tokens.
     * The user must have sufficient available (i.e., not already staked elsewhere) reputation.
     * The ReputationV2 contract needs a way to know how much reputation is "staked" here vs "staked" in its own internal `stakedReputation`
     * if that's used for other purposes.
     * For now, we assume ReputationV2.stake() and ReputationV2.releaseStake() are the primary mechanisms.
     * This contract will call those functions.
     */
    function stakeReputationAndMintTokens(uint256 reputationToStake) external {
        address staker = _msgSender();

        // Check available reputation. ReputationV2.reputationScores() gives total.
        // We need to ensure the user has this amount *available* to be locked.
        // The ReputationSBT (parent of V2) has `stake(user, amount)` and `stakedReputation(user)`.
        // We will use these functions to lock reputation in the ReputationV2 contract itself.
        // The `isTrustedContract` mechanism in ReputationSBT/V2 needs to be set for this OfflineToken contract.

        // This contract needs to be a "trusted contract" in ReputationV2 to call stake/slash.
        reputationContract.stake(staker, reputationToStake); // This will lock reputation in ReputationV2

        stakedReputationByUser[staker] += reputationToStake;
        totalReputationStaked += reputationToStake;

        uint256 tokensToMint = reputationToStake * REPUTATION_TO_TOKEN_RATIO;
        _mint(staker, OFFLINE_TOKEN_ID, tokensToMint, ""); // Mint ERC1155 Offline Tokens

        emit ReputationStaked(staker, reputationToStake, tokensToMint);
    }

    /**
     * @dev Allows a user to burn their Offline Tokens to release their staked reputation.
     */
    function redeemTokensAndReleaseStake(uint256 tokenAmountToBurn) external {
        address redeemer = _msgSender();
        require(balanceOf(redeemer, OFFLINE_TOKEN_ID) >= tokenAmountToBurn, "Insufficient offline tokens");

        uint256 reputationToRelease = tokenAmountToBurn / REPUTATION_TO_TOKEN_RATIO; // Assuming ratio is not zero
        require(stakedReputationByUser[redeemer] >= reputationToRelease, "Not enough reputation staked for this token amount");

        _burn(redeemer, OFFLINE_TOKEN_ID, tokenAmountToBurn); // Burn ERC1155 Offline Tokens

        stakedReputationByUser[redeemer] -= reputationToRelease;
        totalReputationStaked -= reputationToRelease;

        reputationContract.releaseStake(redeemer, reputationToRelease); // Release lock in ReputationV2

        emit StakeReleased(redeemer, reputationToRelease, tokenAmountToBurn);
    }

    /**
     * @dev Allows the Jury contract (or owner if no jury set) to slash a user's staked reputation
     * and burn their corresponding Offline Tokens in case of proven default.
     * @param user The address of the user whose stake is being slashed.
     * @param reputationToSlash The amount of reputation to slash.
     */
    function slashStake(address user, uint256 reputationToSlash) external {
        require(
            msg.sender == juryContractAddress || (juryContractAddress == address(0) && msg.sender == owner()),
            "Caller not authorized to slash stake"
        );
        require(stakedReputationByUser[user] >= reputationToSlash, "Cannot slash more reputation than staked");

        // Slash reputation in ReputationV2 contract first
        // This will also reduce their main reputation score and their stakedReputation there.
        reputationContract.slash(user, reputationToSlash);

        stakedReputationByUser[user] -= reputationToSlash;
        totalReputationStaked -= reputationToSlash;

        // Burn a corresponding amount of Offline Tokens from the user.
        // If the user doesn't have enough tokens (e.g., they transferred them), this part might fail or need adjustment.
        // For simplicity, we burn what they have, up to the equivalent of the slashed reputation.
        uint256 tokensToBurn = reputationToSlash * REPUTATION_TO_TOKEN_RATIO;
        uint256 userOfflineTokenBalance = balanceOf(user, OFFLINE_TOKEN_ID);

        uint256 actualTokensToBurn = (userOfflineTokenBalance < tokensToBurn) ? userOfflineTokenBalance : tokensToBurn;

        if (actualTokensToBurn > 0) {
            _burn(user, OFFLINE_TOKEN_ID, actualTokensToBurn);
        }

        emit StakeSlashed(user, reputationToSlash, actualTokensToBurn);
    }

    /**
     * @dev Required override for ERC1155.
     * Only allows owner to set approval for all, typically for marketplaces or other system contracts.
     * Regular users cannot approve all for offline tokens to prevent accidental transfers if intended as non-transferable.
     * However, ERC1155 by default are transferable. If Offline Tokens should be non-transferable,
     * then _beforeTokenTransfer needs to be overridden similar to ReputationSBT.
     * For now, let's assume they are transferable as per standard ERC1155.
     * FUTURE WORK: Placeholder - ERC1155 tokens are transferable by default.
     * If Offline Tokens are intended to be non-transferable or have restricted transferability (e.g., soulbound, or only transferable back to the contract),
     * the _beforeTokenTransfer function (and potentially _afterTokenTransfer) from ERC1155 must be overridden
     * to enforce these rules, similar to how ReputationSBT makes tokens non-transferable.
     * The current implementation allows free transfer and approval.
     */
    function setApprovalForAll(address operator, bool approved) public override {
        // Optionally restrict who can call this, e.g. only owner or specific system contracts
        // For now, using default OpenZeppelin behavior which allows token holder to approve.
        super.setApprovalForAll(operator, approved);
    }


    // --- Helper Functions ---

    /**
     * @dev Returns the amount of reputation staked by a specific user.
     */
    function getStakedReputation(address user) external view returns (uint256) {
        return stakedReputationByUser[user];
    }

    /**
     * @dev URIs are not dynamically set in this simple version.
     */
    function uri(uint256 /*tokenId*/) public view override returns (string memory) {
        return ""; // Can be updated to return metadata URL if needed
    }
}
