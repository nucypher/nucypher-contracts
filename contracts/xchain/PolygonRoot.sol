// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseRootTunnel.sol";
import "../contracts/coordination/IUpdatableStakeInfo.sol";


contract PolygonRoot is FxBaseRootTunnel, IUpdatableStakeInfo {

    address immutable public source;
    bytes public latestData;

    constructor(
        address _checkpointManager, 
        address _fxRoot,
        address _source
    ) 
        FxBaseRootTunnel(_checkpointManager, _fxRoot) 
    {
        require(_source != address(0), "Wrong input parameters");
        source = _source;
    }

    /**
    * @dev Checks caller is source of data
    */
    modifier onlySource()
    {
        require(msg.sender == source, "Caller must be the source");
        _;
    }

    function _processMessageFromChild(bytes memory data) internal override {
        latestData = data;
    }

    function updateOperator(address stakingProvider, address operator) external override onlySource {
        bytes memory message = abi.encodeWithSelector(IUpdatableStakeInfo.updateOperator.selector, stakingProvider, operator);
        _sendMessageToChild(message);
    }

    function updateAmount(address stakingProvider, uint96 amount) external override onlySource {
        bytes memory message = abi.encodeWithSelector(IUpdatableStakeInfo.updateAmount.selector, stakingProvider, amount);
        _sendMessageToChild(message);
    }

    function batchUpdate(bytes32[] calldata updateInfo) external override onlySource {
        bytes memory message = abi.encodeWithSelector(IUpdatableStakeInfo.batchUpdate.selector, updateInfo);
        _sendMessageToChild(message);
    }
}