// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/coordination/ITACoRootToChild.sol";
import "../contracts/coordination/ITACoChildToRoot.sol";

contract FeeModelForManagedAllowListMock {
    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) external {
        // solhint-disable-previous-line no-empty-blocks
    }

    function beforeIsAuthorized(uint32 ritualId) external view {
        // solhint-disable-previous-line no-empty-blocks
    }
}

contract CoordinatorForManagedAllowListMock {
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
