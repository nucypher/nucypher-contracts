"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import ape
from ape.utils import ZERO_ADDRESS
from web3 import Web3

REWARDS_SLOT = 6
REWARDS_PAID_SLOT = 7
ERROR = 1e5
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")
MIN_OPERATOR_SECONDS = 24 * 60 * 60
REWARD_DURATION = 60 * 60 * 24 * 7  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds


def test_push_reward(accounts, token, threshold_staking, taco_application, chain):
    creator, distributor, staking_provider_1, staking_provider_2, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    reward_portion = min_authorization
    reward_duration = REWARD_DURATION
    value = int(1.5 * min_authorization)

    # Can't push reward without distributor
    token.approve(taco_application.address, reward_portion, sender=creator)
    with ape.reverts():
        taco_application.pushReward(reward_portion, sender=creator)

    # Only owner can set distributor
    with ape.reverts():
        taco_application.setRewardDistributor(distributor, sender=distributor)

    tx = taco_application.setRewardDistributor(distributor, sender=creator)
    assert taco_application.rewardDistributor() == distributor

    events = taco_application.RewardDistributorSet.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["distributor"] == distributor

    # Can't distribute zero rewards
    with ape.reverts():
        taco_application.pushReward(0, sender=distributor)

    # Push reward without staking providers
    token.transfer(distributor, 10 * reward_portion, sender=creator)
    token.approve(taco_application.address, 10 * reward_portion, sender=distributor)
    tx = taco_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert taco_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert taco_application.lastUpdateTime() == timestamp
    assert taco_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(taco_application.address) == reward_portion
    assert token.balanceOf(distributor) == 9 * reward_portion
    assert taco_application.lastTimeRewardApplicable() == timestamp
    assert taco_application.rewardPerTokenStored() == 0
    assert taco_application.rewardPerToken() == 0
    assert taco_application.availableRewards(staking_provider_1) == 0

    events = taco_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait some time and push reward again (without staking providers)
    chain.pending_timestamp += reward_duration // 2 - 1
    tx = taco_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    expected_reward_rate = (reward_portion + reward_portion // 2) * 10**18 // reward_duration
    # Could be some error during calculations
    assert abs(taco_application.rewardRateDecimals() - expected_reward_rate) <= ERROR
    assert taco_application.lastUpdateTime() == timestamp
    assert taco_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(taco_application.address) == 2 * reward_portion
    assert token.balanceOf(distributor) == 8 * reward_portion
    assert taco_application.lastTimeRewardApplicable() == timestamp
    assert taco_application.rewardPerTokenStored() == 0
    assert taco_application.rewardPerToken() == 0
    assert taco_application.availableRewards(staking_provider_1) == 0

    events = taco_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait, add one staking provider and push reward again
    chain.pending_timestamp += reward_duration
    threshold_staking.authorizationIncreased(staking_provider_1, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider_1, staking_provider_1, sender=staking_provider_1)
    taco_application.confirmOperatorAddress(sender=staking_provider_1)

    tx = taco_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert taco_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert taco_application.lastUpdateTime() == timestamp
    assert taco_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(taco_application.address) == 3 * reward_portion
    assert token.balanceOf(distributor) == 7 * reward_portion
    assert taco_application.lastTimeRewardApplicable() == timestamp
    assert taco_application.rewardPerTokenStored() == 0
    assert taco_application.rewardPerToken() == 0
    assert taco_application.availableRewardsed(staking_provider_1) == 0

    events = taco_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait some time and check reward for staking provider
    chain.pending_timestamp += reward_duration // 2
    assert taco_application.rewardPerTokenStored() == 0
    expected_reward_per_token = int(reward_portion * 1e18) // value // 2
    assert abs(taco_application.rewardPerToken() - expected_reward_per_token) < ERROR
    expected_reward = reward_portion // 2
    assert abs(taco_application.availableRewards(staking_provider_1) - expected_reward) < ERROR

    chain.pending_timestamp += reward_duration // 2
    assert taco_application.rewardPerTokenStored() == 0
    expected_reward_per_token = int(reward_portion * 1e18) // value
    reward_per_token = taco_application.rewardPerToken()
    assert abs(reward_per_token - expected_reward_per_token) <= 100
    expected_reward = reward_portion
    reward = taco_application.availableRewards(staking_provider_1)
    assert abs(reward - expected_reward) <= ERROR

    # Add another staking provider without confirmation and push reward again
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    tx = taco_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert taco_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert taco_application.lastUpdateTime() == timestamp
    assert taco_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(taco_application.address) == 4 * reward_portion
    assert token.balanceOf(distributor) == 6 * reward_portion
    assert taco_application.lastTimeRewardApplicable() == timestamp
    assert taco_application.rewardPerTokenStored() == reward_per_token
    assert taco_application.rewardPerToken() == reward_per_token
    assert taco_application.availableRewards(staking_provider_1) == reward
    assert taco_application.availableRewards(staking_provider_2) == 0

    events = taco_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    chain.pending_timestamp += reward_duration
    assert (
        abs(taco_application.availableRewards(staking_provider_1) - (reward + reward_portion))
        < ERROR
    )
    assert taco_application.availableRewards(staking_provider_2) == 0


def test_update_reward(accounts, token, threshold_staking, taco_application, chain):
    creator, distributor, staking_provider_1, staking_provider_2, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    reward_portion = min_authorization
    reward_duration = REWARD_DURATION
    deauthorization_duration = DEAUTHORIZATION_DURATION
    min_operator_seconds = MIN_OPERATOR_SECONDS
    value = int(1.5 * min_authorization)

    reward_per_token = 0
    new_reward_per_token = 0
    staking_provider_1_reward = 0
    staking_provider_1_new_reward = 0
    staking_provider_2_reward = 0
    staking_provider_2_new_reward = 0

    def check_reward_no_confirmation():
        nonlocal reward_per_token, new_reward_per_token
        nonlocal staking_provider_1_reward, staking_provider_1_new_reward

        new_reward_per_token = taco_application.rewardPerToken()
        assert new_reward_per_token > reward_per_token
        assert taco_application.rewardPerTokenStored() == new_reward_per_token
        staking_provider_1_new_reward = taco_application.availableRewards(staking_provider_1)
        assert staking_provider_1_new_reward > staking_provider_1_reward
        assert taco_application.stakingProviderInfo(staking_provider_1)[REWARDS_SLOT] == 0
        assert taco_application.stakingProviderInfo(staking_provider_1)[REWARDS_PAID_SLOT] == 0
        assert taco_application.availableRewards(staking_provider_2) == 0
        assert taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT] == 0
        assert (
            taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
            == new_reward_per_token
        )
        reward_per_token = new_reward_per_token
        staking_provider_1_reward = staking_provider_1_new_reward

    def check_reward_with_confirmation():
        nonlocal reward_per_token, new_reward_per_token, staking_provider_1_reward
        nonlocal staking_provider_1_new_reward, staking_provider_2_reward
        nonlocal staking_provider_2_new_reward

        new_reward_per_token = taco_application.rewardPerToken()
        assert new_reward_per_token > reward_per_token
        assert taco_application.rewardPerTokenStored() == new_reward_per_token
        staking_provider_1_new_reward = taco_application.availableRewards(staking_provider_1)
        assert staking_provider_1_new_reward > staking_provider_1_reward
        assert taco_application.stakingProviderInfo(staking_provider_1)[REWARDS_SLOT] == 0
        assert taco_application.stakingProviderInfo(staking_provider_1)[REWARDS_PAID_SLOT] == 0
        staking_provider_2_new_reward = taco_application.availableRewards(staking_provider_2)
        assert staking_provider_2_new_reward > staking_provider_2_reward
        assert (
            taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT]
            == staking_provider_2_new_reward
        )
        assert (
            taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
            == new_reward_per_token
        )
        reward_per_token = new_reward_per_token
        staking_provider_1_reward = staking_provider_1_new_reward
        staking_provider_2_reward = staking_provider_2_new_reward

    # Prepare one staking provider and reward
    threshold_staking.authorizationIncreased(staking_provider_1, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider_1, staking_provider_1, sender=staking_provider_1)
    taco_application.confirmOperatorAddress(sender=staking_provider_1)

    taco_application.setRewardDistributor(distributor, sender=creator)
    token.transfer(distributor, 100 * reward_portion, sender=creator)
    token.approve(taco_application.address, 100 * reward_portion, sender=distributor)
    taco_application.pushReward(2 * reward_portion, sender=distributor)
    assert taco_application.rewardPerTokenStored() == 0
    assert taco_application.rewardPerToken() == 0
    assert taco_application.availableRewards(staking_provider_1) == 0

    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet
    threshold_staking.authorizationIncreased(staking_provider_2, 0, 4 * value, sender=creator)
    check_reward_no_confirmation()

    # Add reward, wait and bond operator
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet (need confirmation)
    taco_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    check_reward_no_confirmation()

    # Involuntary decrease without confirmation
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_2, 4 * value, 3 * value, sender=creator
    )
    check_reward_no_confirmation()

    # Request for decrease
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationDecreaseRequested(
        staking_provider_2, 3 * value, 2 * value, sender=creator
    )
    check_reward_no_confirmation()

    # Finish decrease without confirmation
    chain.pending_timestamp += deauthorization_duration
    taco_application.finishAuthorizationDecrease(staking_provider_2, sender=creator)
    check_reward_no_confirmation()

    # Resync without confirmation
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.setAuthorized(staking_provider_2, value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider_2, sender=creator)
    check_reward_no_confirmation()

    # Wait and confirm operator
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet (just confirmed operator)
    taco_application.confirmOperatorAddress(sender=staking_provider_2)
    check_reward_no_confirmation()

    # Increase authorization with confirmation
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationIncreased(staking_provider_2, value, 4 * value, sender=creator)
    check_reward_with_confirmation()

    # Involuntary decrease with confirmation
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_2, 4 * value, 3 * value, sender=creator
    )
    check_reward_with_confirmation()

    # Request for decrease
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationDecreaseRequested(
        staking_provider_2, 3 * value, 2 * value, sender=creator
    )
    check_reward_with_confirmation()

    # Finish decrease with confirmation
    chain.pending_timestamp += deauthorization_duration
    taco_application.finishAuthorizationDecrease(staking_provider_2, sender=creator)
    check_reward_with_confirmation()

    # Resync with confirmation
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.setAuthorized(staking_provider_2, value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider_2, sender=creator)
    check_reward_with_confirmation()

    # Bond operator with confirmation (confirmation will be dropped)
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += min_operator_seconds
    # Reward per token will be updated but nothing earned yet (need confirmation)
    taco_application.bondOperator(staking_provider_2, everyone_else[0], sender=staking_provider_2)
    check_reward_with_confirmation()

    # Push reward wait some time and check that no more reward
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration
    assert taco_application.availableRewards(staking_provider_2) == staking_provider_2_reward
    assert (
        taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT]
        == staking_provider_2_reward
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
        == reward_per_token
    )


def test_withdraw(accounts, token, threshold_staking, taco_application, chain):
    (
        creator,
        distributor,
        staking_provider,
        owner,
        beneficiary,
        authorizer,
        staking_provider_2,
        *everyone_else,
    ) = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    reward_portion = min_authorization
    reward_duration = REWARD_DURATION
    min_operator_seconds = MIN_OPERATOR_SECONDS
    value = int(1.5 * min_authorization)

    # No rewards, no staking providers
    threshold_staking.setRoles(staking_provider, owner, beneficiary, authorizer, sender=creator)
    with ape.reverts():
        taco_application.withdrawRewards(staking_provider, sender=beneficiary)

    # Prepare one staking provider and reward
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    taco_application.confirmOperatorAddress(sender=staking_provider)

    # Nothing earned yet
    with ape.reverts():
        taco_application.withdrawRewards(staking_provider, sender=beneficiary)

    taco_application.setRewardDistributor(distributor, sender=creator)
    token.transfer(distributor, 100 * reward_portion, sender=creator)
    token.approve(taco_application.address, 100 * reward_portion, sender=distributor)
    taco_application.pushReward(reward_portion, sender=distributor)
    assert taco_application.rewardPerTokenStored() == 0
    assert taco_application.rewardPerToken() == 0
    assert taco_application.availableRewards(staking_provider) == 0

    chain.pending_timestamp += reward_duration
    # Only beneficiary can withdraw reward
    with ape.reverts():
        taco_application.withdrawRewards(staking_provider, sender=owner)
    with ape.reverts():
        taco_application.withdrawRewards(staking_provider, sender=authorizer)

    reward_per_token = taco_application.rewardPerToken()
    assert reward_per_token > 0
    earned = taco_application.availableRewards(staking_provider)
    assert earned > 0

    tx = taco_application.withdrawRewards(staking_provider, sender=beneficiary)
    assert taco_application.rewardPerTokenStored() == reward_per_token
    assert taco_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == 0
    assert (
        taco_application.stakingProviderInfo(staking_provider)[REWARDS_PAID_SLOT]
        == reward_per_token
    )
    assert token.balanceOf(beneficiary) == earned
    assert token.balanceOf(taco_application.address) == reward_portion - earned

    events = taco_application.RewardPaid.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["beneficiary"] == beneficiary
    assert event["reward"] == earned

    # Add one more staking provider, push reward again and drop operator
    chain.pending_timestamp += min_operator_seconds
    threshold_staking.setRoles(staking_provider_2, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    taco_application.confirmOperatorAddress(sender=staking_provider_2)
    taco_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    taco_application.bondOperator(staking_provider, ZERO_ADDRESS, sender=staking_provider)

    new_earned = taco_application.availableRewards(staking_provider)
    assert taco_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == new_earned

    # Withdraw
    chain.pending_timestamp += reward_duration // 2
    assert taco_application.availableRewards(staking_provider) == new_earned
    tx = taco_application.withdraw(staking_provider, sender=beneficiary)
    new_reward_per_token = taco_application.rewardPerToken()
    assert taco_application.rewardPerTokenStored() == new_reward_per_token
    assert taco_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == 0
    assert (
        taco_application.stakingProviderInfo(staking_provider)[REWARDS_PAID_SLOT]
        == new_reward_per_token
    )
    assert token.balanceOf(beneficiary) == earned + new_earned
    assert token.balanceOf(taco_application.address) == 2 * reward_portion - earned - new_earned

    events = taco_application.RewardPaid.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["beneficiary"] == beneficiary
    assert event["reward"] == new_earned
