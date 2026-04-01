// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract Periods {
    uint256 public constant REWARD_DELAY_PERIODS = 2;

    uint256 public immutable genesisTime;
    uint256 public immutable periodDuration;

    constructor(uint256 _genesisTime, uint256 _periodDuration) {
        require(_periodDuration > 0, "Invalid period duration");
        genesisTime = _genesisTime;
        periodDuration = _periodDuration;
        require(getCurrentPeriod() >= REWARD_DELAY_PERIODS, "genesisTime must be in the past");
    }

    function getPeriodForTimestamp(uint256 timestamp) public view returns (uint256) {
        require(timestamp >= genesisTime, "Timestamp is before genesis");
        return (timestamp - genesisTime) / periodDuration;
    }

    function getCurrentPeriod() public view returns (uint256) {
        return getPeriodForTimestamp(block.timestamp);
    }

    function getCurrentPaymentPeriod() public view returns (uint256) {
        return getCurrentPeriod() - REWARD_DELAY_PERIODS;
    }
}
