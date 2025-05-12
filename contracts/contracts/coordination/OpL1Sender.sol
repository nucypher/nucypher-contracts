// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./ICrossDomainMessenger.sol";

contract OpL1Sender {
    address public messenger;
    address public l2Receiver;

    constructor(address _messenger, address _l2Receiver) {
        messenger = _messenger;
        l2Receiver = _l2Receiver;
    }

    function sendExecution(address targetOnL2, bytes calldata callData, uint32 gasLimit) external {
        bytes memory payload = abi.encode(targetOnL2, callData);
        bytes memory message = abi.encodeWithSignature("execute(bytes)", payload);
        ICrossDomainMessenger(messenger).sendMessage(l2Receiver, message, gasLimit);
    }
}
