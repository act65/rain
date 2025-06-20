// File: contracts/InsuranceDAO.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CurrencyToken.sol";
import "./ReputationSBT.sol";

/**
 * @title InsuranceDAO
 * @dev A DAO for a community insurance pool. Voting power is weighted by reputation.
 */
contract InsuranceDAO {
    // --- State Variables ---
    CurrencyToken public currencyToken;
    ReputationSBT public reputationSBT;

    enum ClaimStatus { Pending, Approved, Rejected, Executed }

    struct Claim {
        uint256 id;
        address claimant;
        uint256 amount;
        string description;
        ClaimStatus status;
        uint256 approvalVotes; // Weighted votes
        uint256 rejectionVotes; // Weighted votes
    }

    mapping(address => uint256) public contributions;
    mapping(uint256 => Claim) public claims;
    mapping(uint256 => mapping(address => bool)) public hasVoted; // Track if a user has voted on a claim
    uint256 public nextClaimId;
    uint256 public approvalQuorum; // Minimum weighted approval votes needed

    // --- Events ---
    event Contribution(address indexed member, uint256 amount);
    event ClaimSubmitted(uint256 claimId, address indexed claimant, uint256 amount);
    event VotedOnClaim(uint256 claimId, address indexed voter, bool approved, uint256 voteWeight);
    event ClaimExecuted(uint256 claimId);

    // --- Constructor ---
    constructor(address _currencyTokenAddress, address _reputationSBTAddress, uint256 _approvalQuorum) {
        currencyToken = CurrencyToken(_currencyTokenAddress);
        reputationSBT = ReputationSBT(_reputationSBTAddress);
        approvalQuorum = _approvalQuorum;
    }

    // --- Core Functions ---

    /**
     * @dev Contribute to the insurance pool to become a member.
     */
    function contribute(uint256 _amount) external {
        contributions[msg.sender] += _amount;
        require(currencyToken.transferFrom(msg.sender, address(this), _amount), "Contribution transfer failed");
        emit Contribution(msg.sender, _amount);
    }

    /**
     * @dev A member submits a claim for a loss.
     */
    function submitClaim(uint256 _amount, string memory _description) external {
        require(contributions[msg.sender] > 0, "Must be a member to submit a claim");
        
        claims[nextClaimId] = Claim({
            id: nextClaimId,
            claimant: msg.sender,
            amount: _amount,
            description: _description,
            status: ClaimStatus.Pending,
            approvalVotes: 0,
            rejectionVotes: 0
        });

        emit ClaimSubmitted(nextClaimId, msg.sender, _amount);
        nextClaimId++;
    }

    /**
     * @dev Members vote on a claim. Vote weight is their reputation score.
     */
    function voteOnClaim(uint256 _claimId, bool _approve) external {
        Claim storage claim = claims[_claimId];
        require(contributions[msg.sender] > 0, "Must be a member to vote");
        require(claim.status == ClaimStatus.Pending, "Claim is not pending");
        require(!hasVoted[_claimId][msg.sender], "Already voted on this claim");

        uint256 voteWeight = reputationSBT.reputationScores(msg.sender);
        require(voteWeight > 0, "Must have reputation to vote");

        hasVoted[_claimId][msg.sender] = true;

        if (_approve) {
            claim.approvalVotes += voteWeight;
        } else {
            claim.rejectionVotes += voteWeight;
        }
        
        // Check if the claim can be moved to Approved status
        if (claim.approvalVotes >= approvalQuorum) {
            claim.status = ClaimStatus.Approved;
        }

        emit VotedOnClaim(_claimId, msg.sender, _approve, voteWeight);
    }

    /**
     * @dev Executes an approved claim, sending funds to the claimant.
     */
    function executeClaim(uint256 _claimId) external {
        Claim storage claim = claims[_claimId];
        require(claim.status == ClaimStatus.Approved, "Claim is not approved");
        require(currencyToken.balanceOf(address(this)) >= claim.amount, "Insufficient funds in pool");

        claim.status = ClaimStatus.Executed;
        
        // Payout the claim
        currencyToken.transfer(claim.claimant, claim.amount);

        emit ClaimExecuted(_claimId);
    }
}