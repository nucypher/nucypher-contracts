// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseRootTunnel.sol";

contract PolygonRoot is FxBaseRootTunnel {
    address public immutable rootApplication;

    constructor(
        address _checkpointManager,
        address _fxRoot,
        address _rootApplication,
        address _fxChildTunnel
    ) FxBaseRootTunnel(_checkpointManager, _fxRoot) {
        require(
            _rootApplication != address(0) && _fxChildTunnel != address(0),
            "Wrong input parameters"
        );
        rootApplication = _rootApplication;
        fxChildTunnel = _fxChildTunnel;
    }

    function _processMessageFromChild(bytes memory data) internal override {
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, ) = rootApplication.call(data);
        require(success, "Root tx failed");
    }

    fallback() external {
        require(msg.sender == rootApplication, "Caller must be the root app");
        _sendMessageToChild(msg.data);
    }
}
