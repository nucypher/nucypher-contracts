// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "../../threshold/IAccessControlApplication.sol";

/**
* @title IFeeModel
* @notice IFeeModel
*/
interface IFeeModel {
    function currency() external view returns(IERC20);
    function stakes() external view returns(IAccessControlApplication);
    function getRitualInitiationCost(address[] calldata providers, uint32 duration) external view returns(uint256);
}
