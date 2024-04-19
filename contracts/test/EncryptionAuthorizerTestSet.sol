// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract CoordinatorForEncryptionAuthorizerMock {
    uint32 public numberOfRituals;
    mapping(uint32 => address) public getAuthority;
    mapping(uint32 => bool) public isRitualActive;

    function mockNewRitual(address authority) external {
        getAuthority[numberOfRituals] = authority;
        isRitualActive[numberOfRituals] = true;
        numberOfRituals += 1;
    }

    function mockEndRitual(uint32 ritualId) external {
        isRitualActive[ritualId] = false;
    }
}

contract SubscriptionForManagedAllowListMock {
    uint32 public numberOfRituals;
    mapping(uint32 => address) public getAuthority;
    mapping(uint32 => bool) public isRitualActive;

    function mockNewRitual(address authority) external {
        getAuthority[numberOfRituals] = authority;
        isRitualActive[numberOfRituals] = true;
        numberOfRituals += 1;
    }

    function mockEndRitual(uint32 ritualId) external {
        isRitualActive[ritualId] = false;
    }
}
