// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./IFeeModel.sol";
import "../../threshold/IAccessControlApplication.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
* @title FlatRateFeeModel
* @notice FlateRateFeeModel
*/
contract FlatRateFeeModel is IFeeModel {

    IERC20 public immutable currency;
    uint256 public immutable feeRatePerSecond;
    IAccessControlApplication public immutable stakes;

    constructor(IERC20 _currency, uint256 _feeRatePerSecond, address _stakes){
        currency = _currency;
        feeRatePerSecond = _feeRatePerSecond;
        stakes = IAccessControlApplication(_stakes);
    }

    function getRitualInitiationCost(
        address[] calldata providers,
        uint32 duration
    ) external view returns(uint256){
        uint256 size = providers.length;
        require(duration > 0, "Invalid ritual duration");
        require(size > 0, "Invalid ritual size");
        return feeRatePerSecond * size * duration;
    }
}
