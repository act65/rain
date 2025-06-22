// File: contracts/Jury.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "./OfflineToken.sol"; // To call slashStake

/**
 * @title Jury
 * @dev Manages dispute resolution via a jury of staked members.
 */
contract Jury is Ownable {
    using Counters for Counters.Counter;

    IERC20 public usdcToken; // USDC token for staking
    OfflineToken public offlineTokenContract; // To call slashStake on guilty parties

    Counters.Counter private _disputeIds;

    // Minimum USDC stake required to become a juror
    uint256 public minJurorStake;
    // Voting period duration for disputes
    uint256 public votingPeriodDuration; // in seconds
    // Quorum: minimum percentage of total juror voting power (staked amount) needed to validate a dispute outcome (1e18 format)
    uint256 public quorumPercentage; // e.g., 0.1 ether for 10%
    // Threshold: minimum percentage of votes for a specific outcome (e.g., Guilty) to pass (1e18 format)
    uint256 public decisionThresholdPercentage; // e.g., 0.51 ether for 51%

    struct Juror {
        uint256 stakedAmount;
        bool isActive; // Can be set to false if slashed or unstaked
    }

    struct Dispute {
        uint256 id;
        address raisedBy;
        address accusedParty;
        string description;
        uint256 creationTimestamp;
        uint256 votingDeadline;
        bool resolved;
        uint256 votesForGuilty;    // Sum of staked amounts for 'Guilty'
        uint256 votesForInnocent;  // Sum of staked amounts for 'Innocent'
        mapping(address => bool) hasVoted; // Juror address => hasVoted
        uint256 totalVotedStake; // Total stake that participated in voting for this dispute
        uint8 outcome; // 0: Pending, 1: Innocent, 2: Guilty, 3: No Quorum / Hung
    }

    mapping(address => Juror) public jurors;
    mapping(uint256 => Dispute) public disputes;
    uint256 public totalActiveJurorStake; // Sum of stakes of all active jurors

    // Events
    event JurorStaked(address indexed juror, uint256 amount);
    event JurorUnstaked(address indexed juror, uint256 amount);
    event DisputeRaised(uint256 indexed disputeId, address indexed raisedBy, address indexed accusedParty, string description);
    event Voted(uint256 indexed disputeId, address indexed juror, bool voteForGuilty, uint256 stakeWeight);
    event DisputeResolved(uint256 indexed disputeId, uint8 outcome, address indexed accusedParty);
    event StakeSlashedForAccused(uint256 indexed disputeId, address indexed accusedParty, uint256 amountSlashed);

    // Outcomes
    uint8 public constant OUTCOME_PENDING = 0;
    uint8 public constant OUTCOME_INNOCENT = 1;
    uint8 public constant OUTCOME_GUILTY = 2;
    uint8 public constant OUTCOME_NO_QUORUM = 3;


    constructor(
        address _usdcTokenAddress,
        address _offlineTokenContractAddress,
        uint256 _minJurorStake,
        uint256 _votingPeriodDuration,
        uint256 _quorumPercentage,
        uint256 _decisionThresholdPercentage
    ) {
        require(_usdcTokenAddress != address(0) && _offlineTokenContractAddress != address(0), "Token addresses cannot be zero");
        require(_minJurorStake > 0, "Min juror stake must be positive");
        require(_votingPeriodDuration > 0, "Voting period must be positive");
        require(_quorumPercentage > 0 && _quorumPercentage <= 1 ether, "Quorum must be between 0 and 100%");
        require(_decisionThresholdPercentage > 0 && _decisionThresholdPercentage <= 1 ether, "Decision threshold must be between 0 and 100%");

        usdcToken = IERC20(_usdcTokenAddress);
        offlineTokenContract = OfflineToken(_offlineTokenContractAddress);
        minJurorStake = _minJurorStake;
        votingPeriodDuration = _votingPeriodDuration;
        quorumPercentage = _quorumPercentage;
        decisionThresholdPercentage = _decisionThresholdPercentage;
    }

    // --- Juror Management ---

    function stakeToBecomeJuror(uint256 amountUSDC) external {
        require(amountUSDC >= minJurorStake, "Amount is less than minimum juror stake");
        // FUTURE WORK: `accrueInterestIfApplicable()` is a placeholder. If juror stakes are themselves
        // invested (e.g., in a protocol like RainfallPool or Compound/Aave) to earn yield for jurors
        // or the Treasury, the logic for accruing and distributing that interest would be needed here
        // or in the `unstakeFromJury` function.
        accrueInterestIfApplicable();

        Juror storage juror = jurors[_msgSender()];
        require(!juror.isActive, "Already an active juror"); // Or allow top-up

        // Transfer USDC from user to this contract
        require(usdcToken.transferFrom(_msgSender(), address(this), amountUSDC), "USDC transfer for stake failed");

        juror.stakedAmount = amountUSDC;
        juror.isActive = true;
        totalActiveJurorStake += amountUSDC;

        emit JurorStaked(_msgSender(), amountUSDC);
    }

    function unstakeFromJury() external {
        accrueInterestIfApplicable(); // Placeholder

        Juror storage juror = jurors[_msgSender()];
        require(juror.isActive, "Not an active juror");
        // Potentially add checks to prevent unstaking if currently involved in an active, unresolved dispute.

        uint256 amountToReturn = juror.stakedAmount;
        juror.stakedAmount = 0;
        juror.isActive = false;
        totalActiveJurorStake -= amountToReturn;

        // Transfer USDC from this contract back to the user
        require(usdcToken.transfer(_msgSender(), amountToReturn), "USDC transfer for unstake failed");

        emit JurorUnstaked(_msgSender(), amountToReturn);
    }

    function isJuror(address account) public view returns (bool) {
        return jurors[account].isActive;
    }

    function getJurorStake(address account) public view returns (uint256) {
        return jurors[account].stakedAmount;
    }

    // --- Dispute Management ---

    function raiseDispute(address accusedParty, string calldata description, uint256 initialEvidenceId) external {
        // FUTURE WORK: Placeholder - Evidence handling is very basic.
        // `initialEvidenceId` is not currently used. A robust system would involve:
        // - Standardized formats for evidence submission (e.g., IPFS hashes linking to structured data).
        // - Mechanisms for parties to submit further evidence during the dispute.
        // - Potentially confidentiality for sensitive evidence.
        // - Clear rules on evidence admissibility and presentation to jurors.
        require(accusedParty != address(0), "Accused party cannot be zero address");
        require(bytes(description).length > 0, "Description cannot be empty");

        _disputeIds.increment();
        uint256 newDisputeId = _disputeIds.current();

        Dispute storage newDispute = disputes[newDisputeId];
        newDispute.id = newDisputeId;
        newDispute.raisedBy = _msgSender();
        newDispute.accusedParty = accusedParty;
        newDispute.description = description;
        newDispute.creationTimestamp = block.timestamp;
        newDispute.votingDeadline = block.timestamp + votingPeriodDuration;
        newDispute.resolved = false;
        newDispute.votesForGuilty = 0;
        newDispute.votesForInnocent = 0;
        newDispute.totalVotedStake = 0;
        newDispute.outcome = OUTCOME_PENDING;
        // The mapping `newDispute.hasVoted` is automatically initialized.

        emit DisputeRaised(newDisputeId, _msgSender(), accusedParty, description);
    }

    function voteOnDispute(uint256 disputeId, bool voteForGuiltyOutcome) external {
        require(isJuror(_msgSender()), "Caller is not an active juror");
        Dispute storage dispute = disputes[disputeId];
        require(dispute.id != 0, "Dispute does not exist"); // Check if disputeId is valid
        require(block.timestamp <= dispute.votingDeadline, "Voting period has ended");
        require(!dispute.resolved, "Dispute already resolved");
        require(!dispute.hasVoted[_msgSender()], "Juror has already voted on this dispute");

        uint256 jurorStakeWeight = jurors[_msgSender()].stakedAmount;
        require(jurorStakeWeight > 0, "Juror has no stake (should not happen if active)");

        dispute.hasVoted[_msgSender()] = true;
        dispute.totalVotedStake += jurorStakeWeight;

        if (voteForGuiltyOutcome) {
            dispute.votesForGuilty += jurorStakeWeight;
        } else {
            dispute.votesForInnocent += jurorStakeWeight;
        }

        emit Voted(disputeId, _msgSender(), voteForGuiltyOutcome, jurorStakeWeight);
    }

    function tallyVotesAndResolveDispute(uint256 disputeId) external {
        Dispute storage dispute = disputes[disputeId];
        require(dispute.id != 0, "Dispute does not exist");
        require(block.timestamp > dispute.votingDeadline, "Voting period has not yet ended");
        require(!dispute.resolved, "Dispute already resolved");

        dispute.resolved = true;

        // Check for quorum
        uint256 requiredStakeForQuorum = (totalActiveJurorStake * quorumPercentage) / 1 ether;
        if (dispute.totalVotedStake < requiredStakeForQuorum) {
            dispute.outcome = OUTCOME_NO_QUORUM;
            emit DisputeResolved(disputeId, dispute.outcome, dispute.accusedParty);
            return;
        }

        // Determine outcome based on threshold
        if (dispute.votesForGuilty * 1 ether / dispute.totalVotedStake >= decisionThresholdPercentage) {
            dispute.outcome = OUTCOME_GUILTY;
            // Execute action for guilty verdict - e.g., slash stake of accused party
            _handleGuiltyVerdict(disputeId, dispute.accusedParty);
        } else if (dispute.votesForInnocent * 1 ether / dispute.totalVotedStake >= decisionThresholdPercentage) {
            // If not guilty by threshold, and innocent meets threshold (or is implied if only two options)
            dispute.outcome = OUTCOME_INNOCENT;
        } else {
            // Neither side met threshold decisively, could be considered a hung jury / no clear decision
            // For simplicity, if not guilty, treat as innocent or a specific "undecided" outcome.
            // Let's stick to the current logic: if guilty threshold met -> guilty, else innocent (if quorum met).
            // A more robust system might need explicit votes for innocent to also meet a threshold.
            // For now: if not guilty, then innocent (assuming binary choice and quorum met).
            dispute.outcome = OUTCOME_INNOCENT; // Default to innocent if guilty threshold not met
        }

        // FUTURE WORK: Placeholder - Juror reward/slashing is not implemented.
        // A complete system would:
        // 1. Identify jurors who voted with the majority outcome.
        // 2. Reward them (e.g., with a portion of the losing side's stake or from a separate reward pool).
        // 3. Potentially penalize jurors who voted with the minority by slashing a portion of their stake.
        // This often involves a second transaction or more complex logic to iterate through voters post-resolution.

        emit DisputeResolved(disputeId, dispute.outcome, dispute.accusedParty);
    }

    function _handleGuiltyVerdict(uint256 disputeId, address accusedParty) internal {
        // FUTURE WORK: Placeholder - The amount of stake to slash from the accused is fixed (50% of OfflineToken stake).
        // A more flexible system might:
        // - Allow the dispute raiser to specify the amount at stake or potential penalty.
        // - Have different categories of disputes with predefined penalty ranges.
        // - Allow jurors to decide on the penalty amount as part of their deliberation (more complex).
        // - Base the slash amount on the actual damages proven.
        uint256 stakedRepInOfflineContract = offlineTokenContract.getStakedReputation(accusedParty);

        if (stakedRepInOfflineContract > 0) {
            uint256 amountToSlash = stakedRepInOfflineContract / 2; // Slash 50% as an example

            if (amountToSlash > 0) {
                // Before calling slashStake, ensure this Jury contract is authorized in OfflineToken
                // The OfflineToken.setJuryContract() should have been called with this Jury contract's address.
                try offlineTokenContract.slashStake(accusedParty, amountToSlash) {
                    emit StakeSlashedForAccused(disputeId, accusedParty, amountToSlash);
                } catch {
                    // Slashing failed, could emit an event or log.
                }
            }
        }
    }

    // --- Helper/Admin Functions ---

    function setMinJurorStake(uint256 _newMinStake) public onlyOwner {
        require(_newMinStake > 0, "Min juror stake must be positive");
        minJurorStake = _newMinStake;
    }

    function setVotingPeriodDuration(uint256 _newDuration) public onlyOwner {
        require(_newDuration > 0, "Voting period must be positive");
        votingPeriodDuration = _newDuration;
    }

    function setQuorumPercentage(uint256 _newQuorum) public onlyOwner {
        require(_newQuorum > 0 && _newQuorum <= 1 ether, "Quorum must be between 0 and 100%");
        quorumPercentage = _newQuorum;
    }

    function setDecisionThresholdPercentage(uint256 _newThreshold) public onlyOwner {
        require(_newThreshold > 0 && _newThreshold <= 1 ether, "Threshold must be between 0 and 100%");
        decisionThresholdPercentage = _newThreshold;
    }

    function setOfflineTokenContract(address _offlineTokenContractAddress) public onlyOwner {
        require(_offlineTokenContractAddress != address(0), "OfflineToken contract address cannot be zero");
        offlineTokenContract = OfflineToken(_offlineTokenContractAddress);
    }

    function accrueInterestIfApplicable() internal view {
        // Placeholder for if juror stakes were to earn interest from a pool.
        // Not implemented in this version.
    }

    function getDisputeVotes(uint256 disputeId) public view returns (uint256 guiltyVotes, uint256 innocentVotes, uint256 totalStakeVoted) {
        Dispute storage dispute = disputes[disputeId];
        require(dispute.id != 0, "Dispute does not exist");
        return (dispute.votesForGuilty, dispute.votesForInnocent, dispute.totalVotedStake);
    }

    function getDisputeOutcome(uint256 disputeId) public view returns (uint8) {
        Dispute storage dispute = disputes[disputeId];
        require(dispute.id != 0, "Dispute does not exist");
        return dispute.outcome;
    }
}
