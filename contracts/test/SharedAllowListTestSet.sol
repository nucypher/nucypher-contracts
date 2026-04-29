// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/coordination/ITACoRootToChild.sol";
import "../contracts/coordination/ITACoChildToRoot.sol";

contract SharedSubscriptionForSharedAllowListMock {
    mapping(address => bool) public authAdmins;

    function setAuthAdmin(address authAdmin, bool value) external {
        authAdmins[authAdmin] = value;
    }

    function beforeSetAuthorization(
        address authAdmin,
        uint32,
        address[] calldata,
        bool
    ) public virtual {
        require(authAdmins[authAdmin], "Not authorized");
    }

    function beforeIsAuthorized(address authAdmin, uint32) public view {
        require(authAdmins[authAdmin], "Not authorized");
    }
}

contract CoordinatorForSharedAllowListMock {
    uint256 public numberOfRituals = 1; // for check in GlobalAllowLIst constructor

    mapping(uint32 ritualId => address authority) public authorities;
    address public feeModel;

    constructor(address _feeModel) {
        feeModel = _feeModel;
    }

    function initiateRitual(uint32 ritualId, address authority) external {
        authorities[ritualId] = authority;
    }

    function isRitualActive(uint32) external pure returns (bool) {
        return true;
    }

    function getFeeModel(uint32) external view returns (address) {
        return feeModel;
    }

    function getAuthority(uint32 ritualId) external view returns (address) {
        return authorities[ritualId];
    }
}
