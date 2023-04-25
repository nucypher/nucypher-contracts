// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
* @title StakeInfo
* @notice StakeInfo
*/
interface IUpdatableStakes {

    event UpdatedStakeOperator(address indexed stakingProvider, address indexed operator);
    event UpdatedStakeAmount(address indexed stakingProvider, uint96 amount);

    function updateOperator(address stakingProvider, address operator) external;

    function updateAmount(address stakingProvider, uint96 amount) external;

    function batchUpdate(bytes32[] calldata updateInfo) external;
}
