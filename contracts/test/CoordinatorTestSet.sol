// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../threshold/ITACoChildApplication.sol";

/**
 * @notice Contract for testing Coordinator contract
 */
contract ChildApplicationForCoordinatorMock is ITACoChildApplication {
    uint96 public minimumAuthorization = 0;

    mapping(address => uint96) public authorizedStake;
    mapping(address => address) public operatorFromStakingProvider;
    mapping(address => address) public stakingProviderToOperator;
    mapping(address => bool) public confirmations;

    function updateOperator(address _stakingProvider, address _operator) external {
        address oldOperator = operatorFromStakingProvider[_stakingProvider];
        stakingProviderToOperator[oldOperator] = address(0);
        operatorFromStakingProvider[_stakingProvider] = _operator;
        stakingProviderToOperator[_operator] = _stakingProvider;
    }

    function updateAuthorization(address _stakingProvider, uint96 _amount) external {
        authorizedStake[_stakingProvider] = _amount;
    }

    function confirmOperatorAddress(address _operator) external {
        confirmations[_operator] = true;
    }
}

// /**
//  * @notice Intermediary contract for testing operator
//  */
// contract Intermediary {
//     TACoApplication public immutable application;

//     constructor(TACoApplication _application) {
//         application = _application;
//     }

//     function bondOperator(address _operator) external {
//         application.bondOperator(address(this), _operator);
//     }

//     function confirmOperatorAddress() external {
//         application.confirmOperatorAddress();
//     }
// }
