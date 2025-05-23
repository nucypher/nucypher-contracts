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
    address public immutable messenger;
    address public immutable l1Sender;

    event Executed(address target, bytes result);

    /**
     * @param _l1Sender The address of the L1 sender contract.
     * @param _messenger The address of the CrossDomainMessenger contract.
     */
    constructor(address _l1Sender, address _messenger) {
        l1Sender = _l1Sender;
        messenger = _messenger;
    }

    /**
     * @notice Receives data from the L1 sender contract via the messenger.
     * @param data The data sent from the L1 sender contract.
     */
    function recvData(bytes calldata data) external {
        require(messenger == msg.sender, "Not from messenger");
        require(
            l1Sender == ICrossDomainMessenger(messenger).xDomainMessageSender(),
            "Invalid sender"
        );
        (address target, bytes memory callData) = abi.decode(data, (address, bytes));
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, bytes memory result) = target.call(callData);
        require(success, "L2 Receiver Execution failed");

        emit Executed(target, result);
    }
}
