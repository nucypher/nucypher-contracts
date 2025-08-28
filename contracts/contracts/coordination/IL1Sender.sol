// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title IL1Sender
 * @notice Interface for sending data to the L2 receiver contract.
 */
interface IL1Sender {
    /**
     * @notice Sends data to the L2 receiver contract.
     * @param target The address of the target contract on L2.
     * @param data The data to be sent to the target contract.
     */
    function sendData(address target, bytes calldata data) external;
}
