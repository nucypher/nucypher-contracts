// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title ITACoChildToRoot
 * @notice Interface for x-chain interactions from coordinator to application
 */
interface ITACoChildToRoot {
    /**
     * @notice Signals that an operator address is confirmed
     * @param stakingProvider Staking provider address
     * @param operator Operator address
     */
    event OperatorConfirmed(address indexed stakingProvider, address indexed operator);

    function confirmOperatorAddress(address operator) external;
}
