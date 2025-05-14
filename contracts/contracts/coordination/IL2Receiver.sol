// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title IL2Receiver
 * @notice Interface for receiving data from the L1 sender contract.
 */
interface IL2Receiver {
    /**
     * @notice Receives data from the L1 sender contract.
     * @param data The data sent from the L1 sender contract.
     */
    function recvData(bytes calldata data) external;
}
