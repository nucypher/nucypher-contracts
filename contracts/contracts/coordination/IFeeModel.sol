// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
* @title IFeeModel
* @notice IFeeModel
*/
interface IFeeModel {
    function currency() external pure returns(address);
    function getRitualInitiationCost(address[] calldata providers, uint32 duration) external view returns(uint256);
}
