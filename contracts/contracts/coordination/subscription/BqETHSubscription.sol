// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./StandardSubscription.sol";

/**
 * @title BqETHSubscription
 */
contract BqETHSubscription is StandardSubscription {
    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _accessController The address of the global allow list
     * @param _feeToken The address of the fee token contract
     * @param _adopterSetter Address that can set the adopter address
     * @param _initialBaseFeeRate Fee rate per node per second
     * @param _baseFeeRateIncrease Increase of base fee rate per each period (fraction of INCREASE_BASE)
     * @param _encryptorFeeRate Fee rate per encryptor per second
     * @param _maxNodes Maximum nodes in the package
     * @param _subscriptionPeriodDuration Maximum duration of subscription period
     * @param _yellowPeriodDuration Duration of yellow period
     * @param _redPeriodDuration Duration of red period
     */
    constructor(
        Coordinator _coordinator,
        GlobalAllowList _accessController,
        IERC20 _feeToken,
        address _adopterSetter,
        uint256 _initialBaseFeeRate,
        uint256 _baseFeeRateIncrease,
        uint256 _encryptorFeeRate,
        uint256 _maxNodes,
        uint32 _subscriptionPeriodDuration,
        uint32 _yellowPeriodDuration,
        uint32 _redPeriodDuration
    )
        StandardSubscription(
            _coordinator,
            _accessController,
            _feeToken,
            _adopterSetter,
            _initialBaseFeeRate,
            _baseFeeRateIncrease,
            _encryptorFeeRate,
            _maxNodes,
            _subscriptionPeriodDuration,
            _yellowPeriodDuration,
            _redPeriodDuration
        )
    {}

    /// @dev use `upgradeAndCall` for upgrading together with re-initialization
    function reinitialize() external reinitializer(2) {
        startOfSubscription = uint32(block.timestamp);
    }

    function getCurrentPeriodNumber() public view override returns (uint256) {
        return super.getCurrentPeriodNumber() + 1;
    }
}
