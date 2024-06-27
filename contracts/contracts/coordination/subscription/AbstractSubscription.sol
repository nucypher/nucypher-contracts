// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../Coordinator.sol";
import "../IFeeModel.sol";

/**
 * @title Base Subscription contract
 * @notice Manages the subscription information for rituals.
 */
abstract contract AbstractSubscription is IFeeModel {
    Coordinator public immutable coordinator;

    uint32 public immutable subscriptionPeriodDuration;
    uint32 public immutable yellowPeriodDuration;
    uint32 public immutable redPeriodDuration;

    uint256[20] private gap;

    /**
     * @notice Sets subscription parameters
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _subscriptionPeriodDuration Maximum duration of subscription period
     * @param _yellowPeriodDuration Duration of yellow period
     * @param _redPeriodDuration Duration of red period
     */
    constructor(
        Coordinator _coordinator,
        uint32 _subscriptionPeriodDuration,
        uint32 _yellowPeriodDuration,
        uint32 _redPeriodDuration
    ) {
        require(address(_coordinator) != address(0), "Coordinator cannot be the zero address");
        coordinator = _coordinator;
        subscriptionPeriodDuration = _subscriptionPeriodDuration;
        yellowPeriodDuration = _yellowPeriodDuration;
        redPeriodDuration = _redPeriodDuration;
    }

    modifier onlyCoordinator() {
        require(msg.sender == address(coordinator), "Only the Coordinator can call this method");
        _;
    }

    modifier onlyAccessController() virtual;

    modifier onlyActiveRitual(uint32 ritualId) virtual;

    function getEndOfSubscription() public view virtual returns (uint32);

    function processRitualExtending(
        address,
        uint32 ritualId,
        uint256,
        uint32
    ) external view override onlyCoordinator onlyActiveRitual(ritualId) {
        (, uint32 endTimestamp) = coordinator.getTimestamps(ritualId);
        require(
            getEndOfSubscription() + yellowPeriodDuration + redPeriodDuration >= endTimestamp,
            "Ritual parameters exceed available in package"
        );
    }

    /**
     * @dev This function is called before the setAuthorizations function
     */
    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata,
        bool
    ) public virtual override onlyAccessController onlyActiveRitual(ritualId) {
        require(block.timestamp <= getEndOfSubscription(), "Subscription has expired");
    }

    /**
     * @dev This function is called before the isAuthorized function
     * @param ritualId The ID of the ritual
     */
    function beforeIsAuthorized(
        uint32 ritualId
    ) public view virtual override onlyAccessController onlyActiveRitual(ritualId) {
        require(
            block.timestamp <= getEndOfSubscription() + yellowPeriodDuration,
            "Yellow period has expired"
        );
    }
}
