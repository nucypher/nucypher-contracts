// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseRootTunnel.sol";


contract PolygonRoot is FxBaseRootTunnel {
    bytes public latestData;

    constructor(address _checkpointManager, address _fxRoot) FxBaseRootTunnel(_checkpointManager, _fxRoot) {}

    function _processMessageFromChild(bytes memory data) internal override {
        latestData = data;
    }

    function updateOperator(address stakingProvider, address operator) public {
        bytes memory message = abi.encodeWithSignature("updateOperator(address,address)", stakingProvider, operator);
        _sendMessageToChild(message);
    }

    function updateAmount(address stakingProvider, uint96 amount) public {
        bytes memory message = abi.encodeWithSignature("updateAmount(address,uint96)", stakingProvider, amount);
        _sendMessageToChild(message);
    }

    function batchUpdate(bytes32[] calldata updateInfo) public {
        bytes memory message = abi.encodeWithSignature("batchUpdate(bytes32[])", updateInfo);
        _sendMessageToChild(message);
    }
}