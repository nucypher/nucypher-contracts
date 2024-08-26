// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../lib/LookupKey.sol";
import "./GlobalAllowList.sol";
import "./Coordinator.sol";
import {UpfrontSubscriptionWithEncryptorsCap} from "./subscription/Subscription.sol";

/**
 * @title ManagedAllowList
 * @notice Manages a list of addresses that are authorized to decrypt ciphertexts, with additional management features.
 * This contract extends the GlobalAllowList contract and introduces additional management features.
 * It maintains a reference to a Subscription contract, which is used to manage the authorization caps for different addresses and rituals.
 * The Subscription contract is used to enforce limits on the number of authorization actions that can be performed, and these limits can be set and updated through the ManagedAllowList contract.
 */
contract ManagedAllowList is GlobalAllowList {
    mapping(bytes32 => uint256) internal allowance;

    /**
     * @notice The Subscription contract used to manage authorization caps
     */
    // TODO: Should it be updatable?
    UpfrontSubscriptionWithEncryptorsCap public immutable subscription;

    /**
     * @notice Emitted when an administrator cap is set
     * @param ritualId The ID of the ritual
     * @param _address The address of the administrator
     * @param cap The cap value
     */
    event AdministratorCapSet(uint32 indexed ritualId, address indexed _address, uint256 cap);

    /**
     * @notice Sets the coordinator and subscription contracts
     * @dev The coordinator and subscription contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _subscription The address of the subscription contract
     */
    constructor(
        Coordinator _coordinator,
        UpfrontSubscriptionWithEncryptorsCap _subscription // TODO replace with IFeeModel subscription
    ) GlobalAllowList(_coordinator) {
        require(address(_subscription) != address(0), "Subscription cannot be the zero address");
        subscription = _subscription;
    }

    /**
     * @notice Checks if the sender is the authority of the ritual
     * @param ritualId The ID of the ritual
     */
    modifier onlyCohortAuthority(uint32 ritualId) {
        require(
            coordinator.getAuthority(ritualId) == msg.sender,
            "Only cohort authority is permitted"
        );
        _;
    }

    /**
     * @notice Checks if the sender has allowance to set authorizations
     * @dev This function overrides the canSetAuthorizations modifier in the GlobalAllowList contract
     * @param ritualId The ID of the ritual
     */
    modifier canSetAuthorizations(uint32 ritualId) override {
        require(getAllowance(ritualId, msg.sender) > 0, "Only administrator is permitted");
        _;
    }

    /**
     * @notice Returns the allowance of an administrator for a ritual
     * @param ritualId The ID of the ritual
     * @param admin The address of the administrator
     * @return The allowance of the administrator
     */
    function getAllowance(uint32 ritualId, address admin) public view returns (uint256) {
        return allowance[LookupKey.lookupKey(ritualId, admin)];
    }

    /**
     * @dev This function is called before the setAuthorizations function
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     * @param value The authorization status
     */
    function _beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        // TODO: Currently unused, remove?
        bool value
    ) internal override {
        super._beforeSetAuthorization(ritualId, addresses, value);
        for (uint256 i = 0; i < addresses.length; i++) {
            require(
                authActions[ritualId] <
                    subscription.authorizationActionsCap(ritualId, addresses[i]),
                "Authorization cap exceeded"
            );
        }
    }

    /**
     * @notice Sets the administrator caps for a ritual
     * @dev Only active rituals can set administrator caps
     * @param ritualId The ID of the ritual
     * @param addresses The addresses of the administrators
     * @param value The cap value
     */
    function setAdministratorCaps(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 value
    ) internal {
        require(
            coordinator.isRitualActive(ritualId),
            "Only active rituals can set administrator caps"
        );
        for (uint256 i = 0; i < addresses.length; i++) {
            allowance[LookupKey.lookupKey(ritualId, addresses[i])] = value;
            emit AdministratorCapSet(ritualId, addresses[i], value);
        }
        authActions[ritualId] += addresses.length;
    }

    /**
     * @notice Adds administrators for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses of the administrators
     * @param cap The cap value
     */
    function addAdministrators(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 cap
    ) external onlyCohortAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, cap);
    }

    /**
     * @notice Removes administrators for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses of the administrators
     */
    function removeAdministrators(
        uint32 ritualId,
        address[] calldata addresses
    ) external onlyCohortAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, 0);
    }
}
