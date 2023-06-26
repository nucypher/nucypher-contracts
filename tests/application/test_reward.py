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


def test_push_reward(accounts, token, threshold_staking, pre_application, chain):
    creator, distributor, staking_provider_1, staking_provider_2, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    reward_portion = min_authorization
    reward_duration = REWARD_DURATION
    value = int(1.5 * min_authorization)

    # Can't push reward without distributor
    token.approve(pre_application.address, reward_portion, sender=creator)
    with ape.reverts():
        pre_application.pushReward(reward_portion, sender=creator)

    # Only owner can set distributor
    with ape.reverts():
        pre_application.setRewardDistributor(distributor, sender=distributor)

    tx = pre_application.setRewardDistributor(distributor, sender=creator)
    assert pre_application.rewardDistributor() == distributor

    events = pre_application.RewardDistributorSet.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["distributor"] == distributor

    # Can't distribute zero rewards
    with ape.reverts():
        pre_application.pushReward(0, sender=distributor)

    # Push reward without staking providers
    token.transfer(distributor, 10 * reward_portion, sender=creator)
    token.approve(pre_application.address, 10 * reward_portion, sender=distributor)
    tx = pre_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert pre_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert pre_application.lastUpdateTime() == timestamp
    assert pre_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(pre_application.address) == reward_portion
    assert token.balanceOf(distributor) == 9 * reward_portion
    assert pre_application.lastTimeRewardApplicable() == timestamp
    assert pre_application.rewardPerTokenStored() == 0
    assert pre_application.rewardPerToken() == 0
    assert pre_application.earned(staking_provider_1) == 0

    events = pre_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait some time and push reward again (without staking providers)
    chain.pending_timestamp += reward_duration // 2 - 1
    tx = pre_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    expected_reward_rate = (reward_portion + reward_portion // 2) * 10**18 // reward_duration
    # Could be some error during calculations
    assert abs(pre_application.rewardRateDecimals() - expected_reward_rate) <= ERROR
    assert pre_application.lastUpdateTime() == timestamp
    assert pre_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(pre_application.address) == 2 * reward_portion
    assert token.balanceOf(distributor) == 8 * reward_portion
    assert pre_application.lastTimeRewardApplicable() == timestamp
    assert pre_application.rewardPerTokenStored() == 0
    assert pre_application.rewardPerToken() == 0
    assert pre_application.earned(staking_provider_1) == 0

    events = pre_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait, add one staking provider and push reward again
    chain.pending_timestamp += reward_duration
    threshold_staking.authorizationIncreased(staking_provider_1, 0, value, sender=creator)
    pre_application.bondOperator(staking_provider_1, staking_provider_1, sender=staking_provider_1)
    pre_application.confirmOperatorAddress(sender=staking_provider_1)

    tx = pre_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert pre_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert pre_application.lastUpdateTime() == timestamp
    assert pre_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(pre_application.address) == 3 * reward_portion
    assert token.balanceOf(distributor) == 7 * reward_portion
    assert pre_application.lastTimeRewardApplicable() == timestamp
    assert pre_application.rewardPerTokenStored() == 0
    assert pre_application.rewardPerToken() == 0
    assert pre_application.earned(staking_provider_1) == 0

    events = pre_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    # Wait some time and check reward for staking provider
    chain.pending_timestamp += reward_duration // 2
    assert pre_application.rewardPerTokenStored() == 0
    expected_reward_per_token = int(reward_portion * 1e18) // value // 2
    assert abs(pre_application.rewardPerToken() - expected_reward_per_token) < ERROR
    expected_reward = reward_portion // 2
    assert abs(pre_application.earned(staking_provider_1) - expected_reward) < ERROR

    chain.pending_timestamp += reward_duration // 2
    assert pre_application.rewardPerTokenStored() == 0
    expected_reward_per_token = int(reward_portion * 1e18) // value
    reward_per_token = pre_application.rewardPerToken()
    assert abs(reward_per_token - expected_reward_per_token) <= 100
    expected_reward = reward_portion
    reward = pre_application.earned(staking_provider_1)
    assert abs(reward - expected_reward) <= ERROR

    # Add another staking provider without confirmation and push reward again
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    tx = pre_application.pushReward(reward_portion, sender=distributor)
    timestamp = chain.pending_timestamp - 1
    assert pre_application.rewardRateDecimals() == reward_portion * 10**18 // reward_duration
    assert pre_application.lastUpdateTime() == timestamp
    assert pre_application.periodFinish() == (timestamp + reward_duration)
    assert token.balanceOf(pre_application.address) == 4 * reward_portion
    assert token.balanceOf(distributor) == 6 * reward_portion
    assert pre_application.lastTimeRewardApplicable() == timestamp
    assert pre_application.rewardPerTokenStored() == reward_per_token
    assert pre_application.rewardPerToken() == reward_per_token
    assert pre_application.earned(staking_provider_1) == reward
    assert pre_application.earned(staking_provider_2) == 0

    events = pre_application.RewardAdded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["reward"] == reward_portion

    chain.pending_timestamp += reward_duration
    assert abs(pre_application.earned(staking_provider_1) - (reward + reward_portion)) < ERROR
    assert pre_application.earned(staking_provider_2) == 0


def test_update_reward(accounts, token, threshold_staking, pre_application, chain):
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

        new_reward_per_token = pre_application.rewardPerToken()
        assert new_reward_per_token > reward_per_token
        assert pre_application.rewardPerTokenStored() == new_reward_per_token
        staking_provider_1_new_reward = pre_application.earned(staking_provider_1)
        assert staking_provider_1_new_reward > staking_provider_1_reward
        assert pre_application.stakingProviderInfo(staking_provider_1)[REWARDS_SLOT] == 0
        assert pre_application.stakingProviderInfo(staking_provider_1)[REWARDS_PAID_SLOT] == 0
        assert pre_application.earned(staking_provider_2) == 0
        assert pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT] == 0
        assert (
            pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
            == new_reward_per_token
        )
        reward_per_token = new_reward_per_token
        staking_provider_1_reward = staking_provider_1_new_reward

    def check_reward_with_confirmation():
        nonlocal reward_per_token, new_reward_per_token, staking_provider_1_reward
        nonlocal staking_provider_1_new_reward, staking_provider_2_reward
        nonlocal staking_provider_2_new_reward

        new_reward_per_token = pre_application.rewardPerToken()
        assert new_reward_per_token > reward_per_token
        assert pre_application.rewardPerTokenStored() == new_reward_per_token
        staking_provider_1_new_reward = pre_application.earned(staking_provider_1)
        assert staking_provider_1_new_reward > staking_provider_1_reward
        assert pre_application.stakingProviderInfo(staking_provider_1)[REWARDS_SLOT] == 0
        assert pre_application.stakingProviderInfo(staking_provider_1)[REWARDS_PAID_SLOT] == 0
        staking_provider_2_new_reward = pre_application.earned(staking_provider_2)
        assert staking_provider_2_new_reward > staking_provider_2_reward
        assert (
            pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT]
            == staking_provider_2_new_reward
        )
        assert (
            pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
            == new_reward_per_token
        )
        reward_per_token = new_reward_per_token
        staking_provider_1_reward = staking_provider_1_new_reward
        staking_provider_2_reward = staking_provider_2_new_reward

    # Prepare one staking provider and reward
    threshold_staking.authorizationIncreased(staking_provider_1, 0, value, sender=creator)
    pre_application.bondOperator(staking_provider_1, staking_provider_1, sender=staking_provider_1)
    pre_application.confirmOperatorAddress(sender=staking_provider_1)

    pre_application.setRewardDistributor(distributor, sender=creator)
    token.transfer(distributor, 100 * reward_portion, sender=creator)
    token.approve(pre_application.address, 100 * reward_portion, sender=distributor)
    pre_application.pushReward(2 * reward_portion, sender=distributor)
    assert pre_application.rewardPerTokenStored() == 0
    assert pre_application.rewardPerToken() == 0
    assert pre_application.earned(staking_provider_1) == 0

    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet
    threshold_staking.authorizationIncreased(staking_provider_2, 0, 4 * value, sender=creator)
    check_reward_no_confirmation()

    # Add reward, wait and bond operator
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet (need confirmation)
    pre_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    check_reward_no_confirmation()

    # Involuntary decrease without confirmation
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_2, 4 * value, 3 * value, sender=creator
    )
    check_reward_no_confirmation()

    # Request for decrease
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationDecreaseRequested(
        staking_provider_2, 3 * value, 2 * value, sender=creator
    )
    check_reward_no_confirmation()

    # Finish decrease without confirmation
    chain.pending_timestamp += deauthorization_duration
    pre_application.finishAuthorizationDecrease(staking_provider_2, sender=creator)
    check_reward_no_confirmation()

    # Resync without confirmation
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.setAuthorized(staking_provider_2, value, sender=creator)
    pre_application.resynchronizeAuthorization(staking_provider_2, sender=creator)
    check_reward_no_confirmation()

    # Wait and confirm operator
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    # Reward per token will be updated but nothing earned yet (just confirmed operator)
    pre_application.confirmOperatorAddress(sender=staking_provider_2)
    check_reward_no_confirmation()

    # Increase authorization with confirmation
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationIncreased(staking_provider_2, value, 4 * value, sender=creator)
    check_reward_with_confirmation()

    # Involuntary decrease with confirmation
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_2, 4 * value, 3 * value, sender=creator
    )
    check_reward_with_confirmation()

    # Request for decrease
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.authorizationDecreaseRequested(
        staking_provider_2, 3 * value, 2 * value, sender=creator
    )
    check_reward_with_confirmation()

    # Finish decrease with confirmation
    chain.pending_timestamp += deauthorization_duration
    pre_application.finishAuthorizationDecrease(staking_provider_2, sender=creator)
    check_reward_with_confirmation()

    # Resync with confirmation
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    threshold_staking.setAuthorized(staking_provider_2, value, sender=creator)
    pre_application.resynchronizeAuthorization(staking_provider_2, sender=creator)
    check_reward_with_confirmation()

    # Bond operator with confirmation (confirmation will be dropped)
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += min_operator_seconds
    # Reward per token will be updated but nothing earned yet (need confirmation)
    pre_application.bondOperator(staking_provider_2, everyone_else[0], sender=staking_provider_2)
    check_reward_with_confirmation()

    # Push reward wait some time and check that no more reward
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration
    assert pre_application.earned(staking_provider_2) == staking_provider_2_reward
    assert (
        pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_SLOT]
        == staking_provider_2_reward
    )
    assert (
        pre_application.stakingProviderInfo(staking_provider_2)[REWARDS_PAID_SLOT]
        == reward_per_token
    )


def test_withdraw(accounts, token, threshold_staking, pre_application, chain):
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
        pre_application.withdraw(staking_provider, sender=beneficiary)

    # Prepare one staking provider and reward
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    pre_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_application.confirmOperatorAddress(sender=staking_provider)

    # Nothing earned yet
    with ape.reverts():
        pre_application.withdraw(staking_provider, sender=beneficiary)

    pre_application.setRewardDistributor(distributor, sender=creator)
    token.transfer(distributor, 100 * reward_portion, sender=creator)
    token.approve(pre_application.address, 100 * reward_portion, sender=distributor)
    pre_application.pushReward(reward_portion, sender=distributor)
    assert pre_application.rewardPerTokenStored() == 0
    assert pre_application.rewardPerToken() == 0
    assert pre_application.earned(staking_provider) == 0

    chain.pending_timestamp += reward_duration
    # Only beneficiary can withdraw reward
    with ape.reverts():
        pre_application.withdraw(staking_provider, sender=owner)
    with ape.reverts():
        pre_application.withdraw(staking_provider, sender=authorizer)

    reward_per_token = pre_application.rewardPerToken()
    assert reward_per_token > 0
    earned = pre_application.earned(staking_provider)
    assert earned > 0

    tx = pre_application.withdraw(staking_provider, sender=beneficiary)
    assert pre_application.rewardPerTokenStored() == reward_per_token
    assert pre_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == 0
    assert (
        pre_application.stakingProviderInfo(staking_provider)[REWARDS_PAID_SLOT] == reward_per_token
    )
    assert token.balanceOf(beneficiary) == earned
    assert token.balanceOf(pre_application.address) == reward_portion - earned

    events = pre_application.RewardPaid.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["beneficiary"] == beneficiary
    assert event["reward"] == earned

    # Add one more staking provider, push reward again and drop operator
    chain.pending_timestamp += min_operator_seconds
    threshold_staking.setRoles(staking_provider_2, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    pre_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    pre_application.confirmOperatorAddress(sender=staking_provider_2)
    pre_application.pushReward(reward_portion, sender=distributor)
    chain.pending_timestamp += reward_duration // 2
    pre_application.bondOperator(staking_provider, ZERO_ADDRESS, sender=staking_provider)

    new_earned = pre_application.earned(staking_provider)
    assert pre_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == new_earned

    # Withdraw
    chain.pending_timestamp += reward_duration // 2
    assert pre_application.earned(staking_provider) == new_earned
    tx = pre_application.withdraw(staking_provider, sender=beneficiary)
    new_reward_per_token = pre_application.rewardPerToken()
    assert pre_application.rewardPerTokenStored() == new_reward_per_token
    assert pre_application.stakingProviderInfo(staking_provider)[REWARDS_SLOT] == 0
    assert (
        pre_application.stakingProviderInfo(staking_provider)[REWARDS_PAID_SLOT]
        == new_reward_per_token
    )
    assert token.balanceOf(beneficiary) == earned + new_earned
    assert token.balanceOf(pre_application.address) == 2 * reward_portion - earned - new_earned

    events = pre_application.RewardPaid.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["beneficiary"] == beneficiary
    assert event["reward"] == new_earned
