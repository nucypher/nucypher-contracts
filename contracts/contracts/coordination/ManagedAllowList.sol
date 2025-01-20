// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/AccessControlUpgradeable.sol";
import "./GlobalAllowList.sol";

/**
 * @title ManagedAllowList
 * @notice Manages a list of addresses that are authorized to decrypt ciphertexts, with additional management features.
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
    constructor(Coordinator _coordinator) GlobalAllowList(_coordinator) {
        _disableInitializers();
    }

    function ritualRole(uint32 ritualId, bytes32 role) public view returns (bytes32) {
        return keccak256(abi.encodePacked(ritualId, role));
    }

    /**
     * Acquire cohort admin role
     * @param ritualId The ID of the ritual
     */
    function initializeCohortAdminRole(uint32 ritualId) external {
        address authority = coordinator.getAuthority(ritualId);
        require(authority == msg.sender, "Only ritual authority is permitted");
        _setRoleAdmin(
            ritualRole(ritualId, AUTH_ADMIN_BASE),
            ritualRole(ritualId, COHORT_ADMIN_BASE)
        );
        _grantRole(ritualRole(ritualId, COHORT_ADMIN_BASE), authority);
    }

    /**
     * @notice Checks if the sender is the authority of the ritual
     * @param ritualId The ID of the ritual
     */
    modifier canSetAuthorizations(uint32 ritualId) virtual override {
        require(
            hasRole(ritualRole(ritualId, AUTH_ADMIN_BASE), msg.sender),
            "Only auth admin is permitted"
        );
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
                "Encryptor must be authorized by the sender first"
            );
        }
        setAuthorizations(ritualId, addresses, false);
    }
}
