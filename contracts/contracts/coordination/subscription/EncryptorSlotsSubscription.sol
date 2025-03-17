// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./AbstractSubscription.sol";

/**
 * @title Subscription that includes payment for enryptor slots
 * @notice Manages the subscription information for rituals.
 */
abstract contract EncryptorSlotsSubscription is AbstractSubscription {
    uint32 public startOfSubscription;
    uint256 public usedEncryptorSlots;
    // example of storage layout
    // mapping(uint256 periodNumber => Billing billing) public billingInfo;

    uint256[20] private gap;

    /**
     * @notice Sets the coordinator and fee token contracts
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
    )
        AbstractSubscription(
            _coordinator,
            _subscriptionPeriodDuration,
            _yellowPeriodDuration,
            _redPeriodDuration
        )
    {}

    function isPeriodPaid(uint256 periodNumber) public view virtual returns (bool);

    function getPaidEncryptorSlots(uint256 periodNumber) public view virtual returns (uint256);

    function getCurrentPeriodNumber() public view virtual returns (uint256) {
        if (startOfSubscription == 0) {
            return 0;
        }
        return (block.timestamp - startOfSubscription) / subscriptionPeriodDuration;
    }

    function getEndOfSubscription() public view override returns (uint32 endOfSubscription) {
        if (startOfSubscription == 0) {
            return 0;
        }

        uint256 currentPeriodNumber = getCurrentPeriodNumber();
        if (currentPeriodNumber == 0 && !isPeriodPaid(currentPeriodNumber)) {
            return 0;
        }

        if (isPeriodPaid(currentPeriodNumber)) {
            while (isPeriodPaid(currentPeriodNumber)) {
                currentPeriodNumber++;
            }
        } else {
            while (!isPeriodPaid(currentPeriodNumber)) {
                currentPeriodNumber--;
            }
            currentPeriodNumber++;
        }
        endOfSubscription = uint32(
            startOfSubscription + currentPeriodNumber * subscriptionPeriodDuration
        );
    }

    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) public virtual override {
        super.beforeSetAuthorization(ritualId, addresses, value);
        if (value) {
            uint256 currentPeriodNumber = getCurrentPeriodNumber();
            uint256 encryptorSlots = isPeriodPaid(currentPeriodNumber)
                ? getPaidEncryptorSlots(currentPeriodNumber)
                : 0;
            usedEncryptorSlots += addresses.length;
            require(usedEncryptorSlots <= encryptorSlots, "Encryptors slots filled up");
        } else {
            if (usedEncryptorSlots >= addresses.length) {
                usedEncryptorSlots -= addresses.length;
            } else {
                usedEncryptorSlots = 0;
            }
        }
    }

    function beforeIsAuthorized(uint32 ritualId) public view virtual override {
        super.beforeIsAuthorized(ritualId);
        // used encryptor slots must be paid
        if (block.timestamp <= getEndOfSubscription()) {
            uint256 currentPeriodNumber = getCurrentPeriodNumber();
            require(
                usedEncryptorSlots <= getPaidEncryptorSlots(currentPeriodNumber),
                "Encryptors slots filled up"
            );
        }
    }
}
