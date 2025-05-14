// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./IL2Receiver.sol";

interface ICrossDomainMessenger {
    function xDomainMessageSender() external view returns (address);
}

/**
 * @title OpL2Receiver
 * @notice Contract is used to receive data from the L1 sender contract via the bridge messenger.
 */
contract OpL2Receiver is IL2Receiver {
    address public messenger;
    address public allowedSender;

    event Executed(address target, bytes result);

    /**
     * @param _messenger The address of the CrossDomainMessenger contract.
     */
    constructor(address _messenger, address _allowedSender) {
        messenger = _messenger;
        allowedSender = _allowedSender;
    }

    /**
     * @notice Receives data from the L1 sender contract via the messenger.
     * @param data The data sent from the L1 sender contract.
     */
    function recvData(bytes calldata data) external {
        require(msg.sender == messenger, "Not from messenger");
        require(
            ICrossDomainMessenger(messenger).xDomainMessageSender() == allowedSender,
            "Invalid sender"
        );

        (address target, bytes memory callData) = abi.decode(data, (address, bytes));
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, bytes memory result) = target.call(callData);
        require(success, "Execution failed");

        emit Executed(target, result);
    }
}
