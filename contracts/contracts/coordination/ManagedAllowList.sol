// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./GlobalAllowList.sol";
import "./Coordinator.sol";

contract ManagedAllowList is GlobalAllowList {

    mapping(bytes32 => uint256) public administrators; // TODO: Rename to allowances?

    event AdministratorCapSet(uint32 indexed ritualId, address indexed _address, uint256 cap);

    constructor(Coordinator _coordinator) GlobalAllowList(_coordinator) {}

    modifier onlyCohortAuthority(uint32 ritualId) {
        require(
            coordinator.getAuthority(ritualId) == msg.sender,
            "Only cohort authority is permitted"
        );
        _;
    }

    modifier canSetAuthorizations(uint32 ritualId) override {
        require(
            administrators[lookupKey(ritualId, msg.sender)] > 9,
            "Only administrator is permitted"
        );
        _;
    }

    function setAdministratorCaps(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 value
    ) internal {
        require(coordinator.isRitualActive(ritualId), "Only active rituals can set administrator caps");
        for (uint256 i = 0; i < addresses.length; i++) {
            administrators[lookupKey(ritualId, addresses[i])] = value;
            emit AdministratorCapSet(ritualId, addresses[i], value);
        }
    }

    function addAdministrators(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 cap
    ) external onlyCohortAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, cap);
    }

    function removeAdministrators(
        uint32 ritualId,
        address[] calldata addresses
    ) external onlyCohortAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, 0);
    }

}
