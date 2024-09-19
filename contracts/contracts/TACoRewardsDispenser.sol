// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity 0.8.23;

contract TACoRewardsDispenser {
    IProxy public claimableRewards; // TODO: what interface to use for claimabeRewards contract?
    IApplication public tacoApplication;

    constructor(IProxy _claimableRewards, IApplication) {
        // TODO: we need some checks here using "require"
        claimableRewards = _claimableRewards;
        tacoApplication = _tacoApplication;
    }

    // TODO: what are the arguments? what is done here?
    function allocatedRewards () {}
}
