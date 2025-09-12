// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title ITACoRootToChild
 * @notice Interface for x-chain interactions from application to coordinator
 */
interface ITACoRootToChild {
    event OperatorUpdated(address indexed stakingProvider, address indexed operator);
    event AuthorizationUpdated(
        address indexed stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization
    );

    function updateOperator(address stakingProvider, address operator) external;

    function updateAuthorization(address stakingProvider, uint96 authorized) external;

    function updateAuthorization(
        address stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization
    ) external;

    function release(address stakingProvider) external;
}
