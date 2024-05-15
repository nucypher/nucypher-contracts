// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseChildTunnel.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PolygonChild is FxBaseChildTunnel, Ownable {
    address public childApplication;

    constructor(address _fxChild) FxBaseChildTunnel(_fxChild) Ownable(msg.sender) {}

    function _processMessageFromRoot(
        uint256 /* stateId */,
        address sender,
        bytes memory data
    ) internal override validateSender(sender) {
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, ) = childApplication.call(data);
        require(success, "Child tx failed");
    }

    function setFxRootTunnel(address _fxRootTunnel) external override onlyOwner {
        require(fxRootTunnel == address(0x0), "FxBaseChildTunnel: ROOT_TUNNEL_ALREADY_SET");
        fxRootTunnel = _fxRootTunnel;
        if (childApplication != address(0)) {
            renounceOwnership();
        }
    }

    function setChildApplication(address _childApplication) public onlyOwner {
        childApplication = _childApplication;
        if (fxRootTunnel != address(0)) {
            renounceOwnership();
        }
    }

    fallback() external {
        require(msg.sender == childApplication, "Only child app can call this method");
        _sendMessageToRoot(msg.data);
    }
}
