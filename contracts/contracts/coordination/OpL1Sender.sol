// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./IL1Sender.sol";
import "./IL2Receiver.sol";

interface ICrossDomainMessenger {
    function sendMessage(address target, bytes calldata message, uint32 gasLimit) external;
}

/**
 * @title OpL1Sender
 * @notice Optimism-based contract responsible for sending data
 *         to the L2 receiver contract via the bridge messenger.
 */
contract OpL1Sender is IL1Sender {
    address public messenger;
    address public l2Receiver;
    uint32 public gasLimit;

    /**
     * @param _messenger The address of the CrossDomainMessenger contract.
     * @param _l2Receiver The address of the L2 receiver contract.
     * @param _gasLimit The gas limit for the message.
     */
    constructor(address _messenger, address _l2Receiver, uint32 _gasLimit) {
        messenger = _messenger;
        l2Receiver = _l2Receiver;
        gasLimit = _gasLimit;
    }

    /**
     * @notice Sends data to the L2 receiver contract via the messenger.
     * @param target The address of the target contract on L2.
     * @param data The data to be sent to the target contract.
     */
    function sendData(address target, bytes calldata data) external {
        bytes memory payload = abi.encode(target, data);
        bytes memory message = abi.encodeWithSelector(IL2Receiver.recvData.selector, payload);
        ICrossDomainMessenger(messenger).sendMessage(l2Receiver, message, gasLimit);
    }
}
