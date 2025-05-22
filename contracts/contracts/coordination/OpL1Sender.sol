// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
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
contract OpL1Sender is IL1Sender, Initializable {
    address public immutable messenger;
    address public immutable dispatcher;
    uint32 public immutable gasLimit;
    address public l2Receiver;

    /**
     * @param _dispatcher The address of the dispatcher contract.
     * @param _messenger The address of the CrossDomainMessenger contract.
     * @param _gasLimit The gas limit for the message.
     */
    constructor(address _dispatcher, address _messenger, uint32 _gasLimit) {
        dispatcher = _dispatcher;
        messenger = _messenger;
        gasLimit = _gasLimit;
    }

    function initialize(address _l2Receiver) external initializer {
        l2Receiver = _l2Receiver;
    }

    /**
     * @notice Sends data to the L2 receiver contract via the messenger.
     * @param target The address of the target contract on L2.
     * @param data The data to be sent to the target contract.
     */
    function sendData(address target, bytes calldata data) external {
        require(dispatcher == msg.sender, "Unauthorized caller");
        bytes memory payload = abi.encode(target, data);
        bytes memory callData = abi.encodeWithSelector(IL2Receiver.recvData.selector, payload);
        ICrossDomainMessenger(messenger).sendMessage(l2Receiver, callData, gasLimit);
    }
}
