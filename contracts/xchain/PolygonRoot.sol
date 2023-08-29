// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseRootTunnel.sol";
import "../contracts/coordination/ITACoRootToChild.sol";

contract PolygonRoot is FxBaseRootTunnel, ITACoRootToChild {
    address public immutable rootApplication;

    constructor(
        address _checkpointManager,
        address _fxRoot,
        address _rootApplication,
        address _fxChildTunnel
    ) FxBaseRootTunnel(_checkpointManager, _fxRoot) {
        require(_rootApplication != address(0), "Wrong input parameters");
        rootApplication = _rootApplication;
        fxChildTunnel = _fxChildTunnel;
    }

    /**
     * @dev Checks caller is the root application
     */
    modifier onlyRootApplication() {
        require(msg.sender == rootApplication, "Caller must be the root app");
        _;
    }

    function _processMessageFromChild(bytes memory data) internal override {
        // solhint-disable-next-line avoid-low-level-calls
        rootApplication.call(data);
    }

    function updateOperator(
        address stakingProvider,
        address operator
    ) external override onlyRootApplication {
        bytes memory message = abi.encodeWithSelector(
            ITACoRootToChild.updateOperator.selector,
            stakingProvider,
            operator
        );
        _sendMessageToChild(message);
    }

    function updateAuthorization(
        address stakingProvider,
        uint96 amount
    ) external override onlyRootApplication {
        bytes memory message = abi.encodeWithSelector(
            ITACoRootToChild.updateAuthorization.selector,
            stakingProvider,
            amount
        );
        _sendMessageToChild(message);
    }
}
