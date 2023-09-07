// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseChildTunnel.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PolygonChild is FxBaseChildTunnel, Ownable {
    address public childApplication;

    constructor(address _fxChild) FxBaseChildTunnel(_fxChild) {}

    function _processMessageFromRoot(
        uint256 /* stateId */,
        address sender,
        bytes memory data
    ) internal override validateSender(sender) {
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, ) = childApplication.call(data);
        require(success, "Child tx failed");
    }

    function setChildApplication(address _childApplication) public onlyOwner {
        childApplication = _childApplication;
    }

    fallback() external {
        require(msg.sender == childApplication, "Only child app can call this method");
        _sendMessageToRoot(msg.data);
    }
}
