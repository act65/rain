// File: contracts/primitives/ReputationUpdater.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";

interface IRainReputation {
    function increaseReputation(address user, uint256 amount, string calldata reason) external;
    function recordBroken(address user, uint256 amount, string calldata reason) external;
}

/**
 * @title ReputationUpdater
 * @dev Receives the results of the off-chain Reputation Oracle and commits them to
 * the on-chain reputation ledger.
 *
 * A kept promise increases its promisor's reputation. A broken one is added to their
 * broken-promise counter; it does not reduce their reputation.
 *
 * Each update is identified by `(user, reason)`, and is applied at most once: the
 * oracle must give every event a unique reason (e.g. "PROMISE_FULFILLED:42").
 * Re-submitting a batch is therefore harmless: updates that were already applied
 * are skipped with an event.
 *
 * This contract does not look at a user's delinquent status. A promise kept while
 * delinquent earns nothing, but that is decided by the oracle from the status at the
 * time the promise was kept, so that the outcome does not depend on when the oracle runs.
 */
contract ReputationUpdater is AccessControl {
    IRainReputation public immutable rainReputation;

    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    // keccak256(user, reason) => has this update been processed?
    mapping(bytes32 => bool) public isProcessed;

    event UpdateSkipped(address indexed user, string reason, string why);

    constructor(address _rainReputationAddress) {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        rainReputation = IRainReputation(_rainReputationAddress);
    }

    struct ReputationUpdate {
        address user;
        uint256 amount;
        string reason;
    }

    function updateKey(address user, string calldata reason) public pure returns (bytes32) {
        return keccak256(abi.encode(user, reason));
    }

    /// @dev Marks the update processed; returns false (and logs) if it already was.
    function _claim(ReputationUpdate calldata update) internal returns (bool) {
        bytes32 key = updateKey(update.user, update.reason);
        if (isProcessed[key]) {
            emit UpdateSkipped(update.user, update.reason, "ALREADY_PROCESSED");
            return false;
        }
        isProcessed[key] = true;
        return true;
    }

    function applyReputationChanges(
        ReputationUpdate[] calldata increases,
        ReputationUpdate[] calldata broken
    ) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");

        for (uint i = 0; i < increases.length; i++) {
            if (!_claim(increases[i])) continue;
            rainReputation.increaseReputation(increases[i].user, increases[i].amount, increases[i].reason);
        }

        for (uint i = 0; i < broken.length; i++) {
            if (!_claim(broken[i])) continue;
            rainReputation.recordBroken(broken[i].user, broken[i].amount, broken[i].reason);
        }
    }
}
