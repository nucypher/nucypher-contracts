// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseChildTunnel.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "../contracts/coordination/ITACoChildToRoot.sol";

contract PolygonChild is ITACoChildToRoot, FxBaseChildTunnel, Ownable {
    address public childApplication;

    constructor(address _fxChild) FxBaseChildTunnel(_fxChild) {}

    function _processMessageFromRoot(
        uint256 /* stateId */,
        address sender,
        bytes memory data
    ) internal override validateSender(sender) {
        // solhint-disable-next-line avoid-low-level-calls
        childApplication.call(data);
    }

    function setChildApplication(address _childApplication) public onlyOwner {
        childApplication = _childApplication;
    }

    function confirmOperatorAddress(address operator) external override {
        require(msg.sender == childApplication, "Only child app can call this method");
        bytes memory message = abi.encodeWithSelector(
            ITACoChildToRoot.confirmOperatorAddress.selector,
            operator
        );
        _sendMessageToRoot(message);
    }
}
