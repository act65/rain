// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @dev Test only. A decay schedule with any values, so that the Treasury can be tested with
 * release rates and intervals that a real RainReputation would not allow (such as releasing
 * the whole fund each cycle).
 */
contract MockDecaySchedule {
    uint256 public immutable decayPeriod;
    uint256 public immutable retentionPerPeriod;

    constructor(uint256 _decayPeriod, uint256 _retentionPerPeriod) {
        decayPeriod = _decayPeriod;
        retentionPerPeriod = _retentionPerPeriod;
    }
}
