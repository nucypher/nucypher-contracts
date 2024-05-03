// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/coordination/ITACoRootToChild.sol";
import "../contracts/coordination/ITACoChildToRoot.sol";

/**
 * @notice Contract for testing TACo child application contract
 */
contract RootApplicationForTACoChildApplicationMock {
    ITACoRootToChild public childApplication;

    mapping(address => bool) public confirmations;
    mapping(address => bool) public penalties;

    function setChildApplication(ITACoRootToChild _childApplication) external {
        childApplication = _childApplication;
    }

    function updateOperator(address _stakingProvider, address _operator) external {
        childApplication.updateOperator(_stakingProvider, _operator);
    }

    function updateAuthorization(address _stakingProvider, uint96 _authorized) external {
        childApplication.updateAuthorization(_stakingProvider, _authorized);
    }

    function updateAuthorization(
        address _stakingProvider,
        uint96 _authorized,
        uint96 _deauthorizing,
        uint64 _endDeauthorization
    ) external {
        childApplication.updateAuthorization(
            _stakingProvider,
            _authorized,
            _deauthorizing,
            _endDeauthorization
        );
    }

    function confirmOperatorAddress(address _operator) external {
        confirmations[_operator] = true;
    }

    function penalize(address _stakingProvider) external {
        penalties[_stakingProvider] = true;
    }

    function resetConfirmation(address _operator) external {
        confirmations[_operator] = false;
    }
}

contract CoordinatorForTACoChildApplicationMock {
    ITACoChildToRoot public immutable application;

    constructor(ITACoChildToRoot _application) {
        application = _application;
    }

    function confirmOperatorAddress(address _operator) external {
        application.confirmOperatorAddress(_operator);
    }
}
