// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract Periods {
    
    uint256 public immutable GENESIS_TIME;
    uint256 public immutable PERIOD_DURATION;

    constructor(uint256 _genesisTime, uint256 _periodDuration) {
        require(_periodDuration > 0, "Invalid period duration");
        GENESIS_TIME = _genesisTime;
        PERIOD_DURATION = _periodDuration;
    }

    function getPeriodForTimestamp(uint256 timestamp) public view returns (uint256) {
        require(timestamp >= GENESIS_TIME, "Timestamp is before genesis");
        return (timestamp - GENESIS_TIME) / PERIOD_DURATION;
    }

    function getCurrentPeriod() public view returns (uint256) {
        return getPeriodForTimestamp(block.timestamp);
    }

}
