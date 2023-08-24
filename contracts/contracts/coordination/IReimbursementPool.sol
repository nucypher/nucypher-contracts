// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title IReimbursementPool
 * @notice IReimbursementPool
 */
interface IReimbursementPool {
    function isAuthorized(address caller) external view returns (bool);

    function refund(uint256 gasSpent, address receiver) external;
}
