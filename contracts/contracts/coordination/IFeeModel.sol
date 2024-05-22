// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title IFeeModel
 * @notice IFeeModel
 */
interface IFeeModel {
    function currency() external view returns (IERC20);

    function getRitualInitiationCost(
        uint256 numberOfProviders,
        uint32 duration
    ) external view returns (uint256);

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external;

    /**
     * @dev This function is called before the setAuthorizations function
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     * @param value The authorization status
     */
    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) external;
}
