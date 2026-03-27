// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/TACoApplication.sol";

/**
 * @notice Contract for testing TACo application contract
 */
contract ChildApplicationForTACoApplicationMock {
    struct StakingProviderInfo {
        uint96 authorized;
        uint96 deauthorizing;
    }

    TACoApplication public immutable rootApplication;

    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    mapping(address => address) public stakingProviderToOperator;
    mapping(address => address) public operatorToStakingProvider;

    mapping(address => bool) public stakingProviderReleased;

    bool public sendRelease;

    constructor(TACoApplication _rootApplication) {
        rootApplication = _rootApplication;
    }

    function updateOperator(address _stakingProvider, address _operator) external {
        address oldOperator = stakingProviderToOperator[_stakingProvider];
        operatorToStakingProvider[oldOperator] = address(0);
        stakingProviderToOperator[_stakingProvider] = _operator;
        operatorToStakingProvider[_operator] = _stakingProvider;
    }

    function updateAuthorization(
        address _stakingProvider,
        uint96 _authorized,
        uint96 _deauthorizing,
        uint64
    ) external {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.authorized = _authorized;
        info.deauthorizing = _deauthorizing;
    }

    function confirmOperatorAddress(address _operator) external {
        rootApplication.confirmOperatorAddress(_operator);
    }

    function setRelease(bool _release) external {
        sendRelease = _release;
    }

    function release(address _stakingProvider) external {
        stakingProviderReleased[_stakingProvider] = true;
        if (sendRelease) {
            rootApplication.release(_stakingProvider);
        }
    }
}
