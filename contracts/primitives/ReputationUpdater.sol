// File: contracts/primitives/ReputationUpdater.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";

// This would be the interface for your final, unified reputation ledger
interface IRainReputation {
    function increaseReputation(address user, uint256 amount, string calldata reason) external;
    function decreaseReputation(address user, uint256 amount, string calldata reason) external;
}

/**
 * @title ReputationUpdater
 * @dev A simple, trusted contract that receives the final results from the off-chain
 * Reputation Oracle and commits them to the on-chain reputation ledger.
 */
contract ReputationUpdater is AccessControl {
    IRainReputation public immutable rainReputation;

    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    constructor(address _rainReputationAddress) {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        rainReputation = IRainReputation(_rainReputationAddress);
    }

    struct ReputationUpdate {
        address user;
        uint256 amount;
        string reason;
    }

    function applyReputationChanges(
        ReputationUpdate[] calldata increases,
        ReputationUpdate[] calldata decreases
    ) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");

        for (uint i = 0; i < increases.length; i++) {
            rainReputation.increaseReputation(
                increases[i].user,
                increases[i].amount,
                increases[i].reason
            );
        }

        for (uint i = 0; i < decreases.length; i++) {
            rainReputation.decreaseReputation(
                decreases[i].user,
                decreases[i].amount,
                decreases[i].reason
            );
        }
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}