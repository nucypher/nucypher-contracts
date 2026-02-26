// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/AccessControlUpgradeable.sol";
import "./GlobalAllowList.sol";

/**
 * @title ManagedAllowList
 * @notice Manages a list of addresses that are authorized to encrypt plaintexts, with additional management features.
 * This contract extends the GlobalAllowList contract and introduces additional management features.
 */
contract ManagedAllowList is GlobalAllowList, AccessControlUpgradeable {
    mapping(address authAdmin => mapping(bytes32 lookupKey => bool)) public authAdmins;

    bytes32 public constant COHORT_ADMIN_BASE = keccak256("COHORT_ADMIN");
    bytes32 public constant AUTH_ADMIN_BASE = keccak256("AUTH_ADMIN");

    /**
     * @notice Sets the coordinator contract
     * @dev The coordinator contract cannot be a zero address and must have a valid number of rituals
     * @param _coordinator The address of the coordinator contract
     */
    constructor(Coordinator _coordinator) GlobalAllowList(_coordinator) {}

    /**
     * Prepares role ID for the specific ritual
     * @param ritualId The ID of the ritual
     * @param role Role ID
     */
    function ritualRole(uint32 ritualId, bytes32 role) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(ritualId, role));
    }

    /**
     * Prepares cohort admin role ID for the specific ritual
     * @param ritualId The ID of the ritual
     */
    function cohortAdminRole(uint32 ritualId) public pure returns (bytes32) {
        return ritualRole(ritualId, COHORT_ADMIN_BASE);
    }

    /**
     * Prepares auth admin role ID for the specific ritual
     * @param ritualId The ID of the ritual
     */
    function authAdminRole(uint32 ritualId) public pure returns (bytes32) {
        return ritualRole(ritualId, AUTH_ADMIN_BASE);
    }

    /**
     * Acquire cohort admin role
     * @param ritualId The ID of the ritual
     */
    function initializeCohortAdminRole(uint32 ritualId) public {
        bytes32 cohortAdminRole = cohortAdminRole(ritualId);
        address authority = coordinator.getAuthority(ritualId);
        require(authority != address(0), "Ritual is not initiated");
        if (hasRole(cohortAdminRole, authority)) {
            return;
        }
        _setRoleAdmin(authAdminRole(ritualId), cohortAdminRole);
        _grantRole(cohortAdminRole, authority);
    }

    /**
     * Grants Auth Admin role. Can be called only by Cohort Admin or Authority of the ritual
     * @dev Automatically grants Cohort Admin role to the authority if was not granted before
     * @param ritualId The ID of the ritual
     * @param account Address for Auth Admin role
     */
    function grantAuthAdminRole(uint32 ritualId, address account) external {
        initializeCohortAdminRole(ritualId);
        grantRole(authAdminRole(ritualId), account);
    }

    /**
     * @notice Checks if the sender is an Authorization Admin of the ritual
     * @param ritualId The ID of the ritual
     */
    modifier canSetAuthorizations(uint32 ritualId) virtual override {
        require(hasRole(authAdminRole(ritualId), msg.sender), "Only auth admin is permitted");
        _;
    }

    /**
     * @notice Authorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     */
    function authorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external override canSetAuthorizations(ritualId) {
        setAuthorizations(ritualId, addresses, true);
        for (uint256 i = 0; i < addresses.length; i++) {
            bytes32 lookupKey = LookupKey.lookupKey(ritualId, addresses[i]);
            authAdmins[msg.sender][lookupKey] = true;
        }
    }

    /**
     * @notice Deauthorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be deauthorized
     */
    function deauthorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external override canSetAuthorizations(ritualId) {
        for (uint256 i = 0; i < addresses.length; i++) {
            bytes32 lookupKey = LookupKey.lookupKey(ritualId, addresses[i]);
            require(
                authAdmins[msg.sender][lookupKey],
                "Encryptor has not been previously authorized by the sender"
            );
        }
        setAuthorizations(ritualId, addresses, false);
    }
}
