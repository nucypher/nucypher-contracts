// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

interface ICrossDomainMessenger {
    function xDomainMessageSender() external view returns (address);
}

contract OpL2Receiver {
    address public messenger;
    address public allowedSender;

    event Executed(address target, bytes result);

    constructor(address _messenger) {
        messenger = _messenger;
    }

    function setAllowedSender(address _allowedSender) external {
        require(allowedSender == address(0), "Allowed sender already set");
        allowedSender = _allowedSender;
    }

    function execute(bytes calldata data) external {
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
