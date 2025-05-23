// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../contracts/coordination/IL2Receiver.sol";

contract MockOpBridgeMessenger is Initializable {
    address public l1Sender;

    function initialize(address _l1Sender) external initializer {
        l1Sender = _l1Sender;
    }

    function xDomainMessageSender() external view returns (address) {
        return l1Sender;
    }

    // solhint-disable-next-line no-unused-vars
    function sendMessage(address target, bytes calldata data, uint32 gasLimit) external {
        require(msg.sender == l1Sender, "Not from L1 sender");
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, ) = target.call(data);
        require(success, "Bridge Execution failed");
    }
}
