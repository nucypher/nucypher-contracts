// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseRootTunnel.sol";


contract PolygonRoot is FxBaseRootTunnel {
    bytes public latestData;

    constructor(address _checkpointManager, address _fxRoot) FxBaseRootTunnel(_checkpointManager, _fxRoot) {}

    function _processMessageFromChild(bytes memory data) internal override {
        latestData = data;
    }

    function updateOperator(address operator, uint8 info) public {
        bytes memory message = abi.encodeWithSignature("updateOperatorInfo(address,uint8)", operator, info);
        _sendMessageToChild(message);
    }

    function batchUpdateOperators(address[] calldata operators, uint8[] calldata infos) public {
        bytes memory message = abi.encodeWithSignature("batchUpdateOperatorInfo(address[],uint8[])", operators, infos);
        _sendMessageToChild(message);
    }
}