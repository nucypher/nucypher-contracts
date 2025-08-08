// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../threshold/ITACoChildApplication.sol";
import "../contracts/coordination/Coordinator.sol";

/**
 * @notice Contract for testing Coordinator contract
 */
contract ChildApplicationForCoordinatorMock is ITACoChildApplication {
    uint96 public minimumAuthorization = 0;

    mapping(address => uint96) public authorizedStake;
    mapping(address => address) public stakingProviderToOperator;
    mapping(address => address) public operatorToStakingProvider;
    mapping(address => bool) public confirmations;

    mapping(address => bool) public stakingProviderReleased;

    function updateOperator(address _stakingProvider, address _operator) external {
        address oldOperator = stakingProviderToOperator[_stakingProvider];
        operatorToStakingProvider[oldOperator] = address(0);
        stakingProviderToOperator[_stakingProvider] = _operator;
        operatorToStakingProvider[_operator] = _stakingProvider;
    }

    function updateAuthorization(address _stakingProvider, uint96 _amount) external {
        authorizedStake[_stakingProvider] = _amount;
    }

    function confirmOperatorAddress(address _operator) external {
        confirmations[_operator] = true;
    }

    // solhint-disable-next-line no-empty-blocks
    function penalize(address _stakingProvider) external {}

    // solhint-disable-next-line no-empty-blocks
    function release(address _stakingProvider) external override {
        stakingProviderReleased[_stakingProvider] = true;
    }
}
