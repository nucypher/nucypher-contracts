// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract TACoRewardsDispenser {
    uint256 public constant REWARDS_CALCULATION_BASE = 10000;
    uint256 public constant ONE_YEAR = 365 * 1 days;
    
    IERC20 public token;
    IProxy public claimableRewards; // TODO: what interface to use for claimabeRewards contract?
    IApplication public tacoApplication;
    // Rewards APY expressed wrt REWARDS_CALCULATION_BASE (e.g. 5% = 500)
    uint256 public rewardsAPY;

    constructor(IERC20 _token, IProxy _claimableRewards, IApplication _tacoApplication, uint256 _rewardsAPY) {
        // TODO: we need some checks here using "require"
        token = _token;
        claimableRewards = _claimableRewards;
        tacoApplication = _tacoApplication;
        rewardsAPY  = _rewardsAPY;
    }

    function dispenseRewardsForCycle() external {
        // This function can only be called once per rewards cycle, so it can be permissionless.
        uint256 periodFinish = tacoApplication.periodFinish();
        require(block.timestamp >= periodFinish);

        // 1. Calculate rewards for this cycle
        uint256 rewardCycleDuration = tacoApplication.rewardDuration();
        uint256 authorizedOverall = tacoApplication.authorizedOverall();

        uint256 rewardsForCycle = authorizedOverall * rewardsAPY * rewardCycleDuration / ONE_YEAR / REWARDS_CALCULATION_BASE;

        // 2. Get rewards from ClaimableRewards (or FutureRewards?)
        token.safeTransferFrom(claimableRewards, address(this), rewardsForCycle);

        // 3. Approve (invariant: before and after this TX this approval is always 0)
        token.approve(tacoApplication, rewardsForCycle);

        // 4. Push rewards for cycle
        tacoApplication.pushReward(rewardsForCycle);
    }
}
