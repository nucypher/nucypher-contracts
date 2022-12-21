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


import brownie
from brownie import Wei, chain

VESTING_RELEASE_TIMESTAMP_SLOT = 9
VESTING_RELEASE_RATE_SLOT = 10
STAKING_PROVIDER_SLOT = 11
ONE_HOUR = 60 * 60


def test_staking_from_worklock(accounts, token, worklock, escrow):
    """
    Tests for staking method: depositFromWorkLock
    """

    creator, staker1, staker2, staker3 = accounts[0:4]

    # Give WorkLock and Staker some coins
    value = Wei("15_000 ether")  # TODO
    token.transfer(worklock.address, 10 * value, {"from": creator})

    # Can't use method not from WorkLock
    with brownie.reverts():
        escrow.depositFromWorkLock(staker1, value, 0, {"from": staker1})
    # Can't deposit 0 tokens
    with brownie.reverts():
        escrow.depositFromWorkLock(staker1, 0, 0, {"from": staker1})
    assert token.balanceOf(escrow.address) == 0

    # First deposit
    tx = worklock.depositFromWorkLock(staker1, value, 0, {"from": creator})
    assert token.balanceOf(escrow.address) == value
    assert escrow.getAllTokens(staker1) == value
    assert escrow.getStakersLength() == 1
    assert escrow.stakers(0) == staker1

    # Check that all events are emitted
    assert "Deposited" in tx.events
    event = tx.events["Deposited"]
    assert event["staker"] == staker1
    assert event["value"] == value

    # Deposit directly and then through WorkLock
    escrow.setStaker(staker2, value, 0, {"from": staker2})
    tx = worklock.depositFromWorkLock(staker2, value, 0, {"from": creator})
    assert token.balanceOf(escrow.address) == 2 * value
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.getStakersLength() == 2
    assert escrow.stakers(1) == staker2

    # Check that all events are emitted
    assert "Deposited" in tx.events
    event = tx.events["Deposited"]
    assert event["staker"] == staker2
    assert event["value"] == value

    # Emulate case when staker withdraws everything and then deposits from WorkLock
    escrow.setStaker(staker3, 0, 1, {"from": staker3})
    tx = worklock.depositFromWorkLock(staker3, value, 0, {"from": creator})
    assert token.balanceOf(escrow.address) == 3 * value
    assert escrow.getAllTokens(staker3) == value
    assert escrow.getStakersLength() == 3
    assert escrow.stakers(2) == staker3

    # Check that all events are emitted
    assert "Deposited" in tx.events
    event = tx.events["Deposited"]
    assert event["staker"] == staker3
    assert event["value"] == value


def test_slashing(accounts, token, worklock, threshold_staking, escrow):
    creator = accounts[0]
    staker = accounts[1]
    investigator = accounts[2]

    # Staker deposits some tokens
    stake = Wei("15_000 ether")  # TODO
    token.transfer(worklock.address, 10 * stake, {"from": creator})
    worklock.depositFromWorkLock(staker, stake, 0, {"from": creator})

    assert stake == escrow.getAllTokens(staker)

    reward = stake // 100
    # Can't slash directly using the escrow contract
    with brownie.reverts():
        escrow.slashStaker(staker, stake, investigator, reward, {"from": creator})
    # Penalty must be greater than zero
    with brownie.reverts():
        threshold_staking.slashStaker(staker, 0, investigator, 0, {"from": creator})

    # Slash the whole stake
    tx = threshold_staking.slashStaker(staker, 2 * stake, investigator, reward, {"from": creator})
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(investigator) == reward

    assert "Slashed" in tx.events
    event = tx.events["Slashed"]
    assert event["staker"] == staker
    assert event["penalty"] == stake
    assert event["investigator"] == investigator
    assert event["reward"] == reward

    # Slash small part
    worklock.depositFromWorkLock(staker, stake, 0, {"from": creator})
    amount_to_slash = stake // 10
    tx = threshold_staking.slashStaker(
        staker, amount_to_slash, investigator, 2 * amount_to_slash, {"from": creator}
    )
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == stake - amount_to_slash
    assert token.balanceOf(investigator) == reward + amount_to_slash

    assert "Slashed" in tx.events
    event = tx.events["Slashed"]
    assert event["staker"] == staker
    assert event["penalty"] == amount_to_slash
    assert event["investigator"] == investigator
    assert event["reward"] == amount_to_slash

    # Slash without reward
    tx = threshold_staking.slashStaker(staker, amount_to_slash, investigator, 0, {"from": creator})
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == stake - 2 * amount_to_slash
    assert token.balanceOf(investigator) == reward + amount_to_slash

    assert "Slashed" in tx.events
    event = tx.events["Slashed"]
    assert event["staker"] == staker
    assert event["penalty"] == amount_to_slash
    assert event["investigator"] == investigator
    assert event["reward"] == 0


def test_request_merge(accounts, threshold_staking, escrow):
    creator, staker1, staker2, staking_provider_1, staking_provider_2 = accounts[0:5]

    # Can't request merge directly
    with brownie.reverts():
        escrow.requestMerge(staker1, staking_provider_1, {"from": creator})

    # Requesting merge for non-existent staker will return zero
    tx = threshold_staking.requestMerge(staker1, staking_provider_1, {"from": creator})
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0

    assert "MergeRequested" in tx.events
    event = tx.events["MergeRequested"]
    assert event["staker"] == staker1
    assert event["stakingProvider"] == staking_provider_1

    # Request can be made several times
    tx = threshold_staking.requestMerge(staker1, staking_provider_1, {"from": creator})
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0
    assert "MergeRequested" not in tx.events

    # Can change provider if old provider has no delegated stake
    tx = threshold_staking.requestMerge(staker1, staker1, {"from": creator})
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staker1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0

    assert "MergeRequested" in tx.events
    event = tx.events["MergeRequested"]
    assert event["staker"] == staker1
    assert event["stakingProvider"] == staker1

    # Requesting merge for existent staker will return stake
    value = 1000
    escrow.setStaker(staker2, value, 0, {"from": creator})
    tx = threshold_staking.requestMerge(staker2, staking_provider_2, {"from": creator})
    assert escrow.getAllTokens(staker2) == value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == value

    assert "MergeRequested" in tx.events
    event = tx.events["MergeRequested"]
    assert event["staker"] == staker2
    assert event["stakingProvider"] == staking_provider_2

    # Request can be made several times
    threshold_staking.requestMerge(staker2, staking_provider_2, {"from": creator})
    assert escrow.getAllTokens(staker2) == value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == value

    escrow.setStaker(staker2, 2 * value, 0, {"from": creator})
    tx = threshold_staking.requestMerge(staker2, staking_provider_2, {"from": creator})
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == 2 * value
    assert "MergeRequested" not in tx.events

    # Request can be done only with the same provider when NU is staked
    with brownie.reverts():
        threshold_staking.requestMerge(staker2, staking_provider_1, {"from": creator})

    # Unstake NU and try again
    threshold_staking.setStakedNu(staking_provider_2, 0, {"from": creator})
    tx = threshold_staking.requestMerge(staker2, staking_provider_1, {"from": creator})
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 2 * value

    assert "MergeRequested" in tx.events
    event = tx.events["MergeRequested"]
    assert event["staker"] == staker2
    assert event["stakingProvider"] == staking_provider_1


def test_withdraw(accounts, token, worklock, threshold_staking, escrow):
    creator, staker, staking_provider = accounts[0:3]

    # Deposit some tokens
    value = Wei(f"{ONE_HOUR} ether")  # Exclude rounding error  # TODO NU(ONE_HOUR, 'NU').to_units()
    token.transfer(worklock.address, 10 * value, {"from": creator})
    worklock.depositFromWorkLock(staker, value + 1, 0, {"from": creator})

    # Withdraw without requesting merge
    tx = escrow.withdraw(1, {"from": staker})
    assert escrow.getAllTokens(staker) == value
    assert token.balanceOf(staker) == 1
    assert token.balanceOf(escrow.address) == value

    assert "Withdrawn" in tx.events
    event = tx.events["Withdrawn"]
    assert event["staker"] == staker
    assert event["value"] == 1

    threshold_staking.requestMerge(staker, staking_provider, {"from": creator})

    # Can't withdraw because everything is staked
    with brownie.reverts():
        escrow.withdraw(1, {"from": staker})

    # Set vesting for the staker
    threshold_staking.setStakedNu(staking_provider, value // 2, {"from": creator})
    now = chain.time() + 1
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR
    escrow.setupVesting([staker], [release_timestamp], [rate], {"from": creator})

    # Vesting parameters prevent from withdrawing
    with brownie.reverts():
        escrow.withdraw(1, {"from": staker})

    # Wait some time
    chain.sleep(40 * 60)
    chain.mine()
    released = value - escrow.getUnvestedTokens(staker)

    # Can't withdraw more than released
    to_withdraw = released
    with brownie.reverts():
        escrow.withdraw(to_withdraw + rate + 1, {"from": staker})

    tx = escrow.withdraw(to_withdraw, {"from": staker})
    assert escrow.getAllTokens(staker) == value - to_withdraw
    assert token.balanceOf(staker) == to_withdraw + 1
    assert token.balanceOf(escrow.address) == value - to_withdraw

    assert "Withdrawn" in tx.events
    event = tx.events["Withdrawn"]
    assert event["staker"] == staker
    assert event["value"] == to_withdraw

    # Can't withdraw more than unstaked
    chain.sleep(30 * 60)
    chain.mine()
    unstaked = value // 2 - to_withdraw
    with brownie.reverts():
        escrow.withdraw(unstaked + 1, {"from": staker})

    # Can't withdraw 0 tokens
    with brownie.reverts():
        escrow.withdraw(0, {"from": staker})

    # Only staker can withdraw stake
    with brownie.reverts():
        escrow.withdraw(1, {"from": staking_provider})

    tx = escrow.withdraw(unstaked, {"from": staker})
    assert escrow.getAllTokens(staker) == value // 2
    assert token.balanceOf(staker) == value // 2 + 1
    assert token.balanceOf(escrow.address) == value // 2

    assert "Withdrawn" in tx.events
    event = tx.events["Withdrawn"]
    assert event["staker"] == staker
    assert event["value"] == unstaked

    # Now unstake and withdraw everything
    threshold_staking.setStakedNu(staking_provider, 0, {"from": creator})
    tx = escrow.withdraw(value // 2, {"from": staker})
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(staker) == value + 1
    assert token.balanceOf(escrow.address) == 0

    assert "Withdrawn" in tx.events
    event = tx.events["Withdrawn"]
    assert event["staker"] == staker
    assert event["value"] == value // 2


def test_vesting(accounts, token, worklock, escrow):
    creator, staker1, staker2, staker3, staker4 = accounts[0:5]

    value = Wei("15_000 ether")  # TODO
    token.transfer(worklock.address, 10 * value, {"from": creator})
    worklock.depositFromWorkLock(staker1, value, 0, {"from": creator})

    now = chain.time()
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR

    # Only owner can set vesting parameters
    with brownie.reverts():
        escrow.setupVesting([staker1], [release_timestamp], [rate], {"from": staker1})

    # All input arrays must have same number of values
    with brownie.reverts():
        escrow.setupVesting(
            [staker1, staker2], [release_timestamp, release_timestamp], [rate], {"from": creator}
        )
    with brownie.reverts():
        escrow.setupVesting(
            [staker1, staker2], [release_timestamp], [rate, rate], {"from": creator}
        )
    with brownie.reverts():
        escrow.setupVesting(
            [staker1], [release_timestamp, release_timestamp], [rate, rate], {"from": creator}
        )

    # At least some amount of tokens must be locked after setting parameters
    with brownie.reverts():
        escrow.setupVesting([staker1], [now], [rate], {"from": creator})
    with brownie.reverts():
        escrow.setupVesting(
            [staker1, staker2],
            [release_timestamp, release_timestamp],
            [rate, rate],
            {"from": creator},
        )

    tx = escrow.setupVesting([staker1], [release_timestamp], [rate], {"from": creator})
    assert escrow.getUnvestedTokens(staker1) == value
    assert escrow.stakerInfo(staker1)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp
    assert escrow.stakerInfo(staker1)[VESTING_RELEASE_RATE_SLOT] == rate

    assert "VestingSet" in tx.events
    event = tx.events["VestingSet"]
    assert event["staker"] == staker1
    assert event["releaseTimestamp"] == release_timestamp
    assert event["releaseRate"] == rate

    chain.mine(timedelta=40 * 60)
    now = chain.time()
    vested = (release_timestamp - now) * rate
    assert escrow.getUnvestedTokens(staker1) == vested

    chain.sleep(20 * 60)
    chain.mine(timedelta=0)
    assert escrow.getUnvestedTokens(staker1) == 0

    # Can't set vesting again even after unlocking
    with brownie.reverts():
        escrow.setupVesting([staker1], [release_timestamp], [rate], {"from": creator})

    # Try again with three other stakers
    value = Wei(f"{ONE_HOUR} ether")  # Exclude rounding error  # TODO NU(ONE_HOUR, 'NU').to_units()
    worklock.depositFromWorkLock(staker2, value, 0, {"from": creator})
    worklock.depositFromWorkLock(staker3, value, 0, {"from": creator})
    worklock.depositFromWorkLock(staker4, value, 0, {"from": creator})

    chain.mine(timedelta=0)
    now = chain.time() + 1
    release_timestamp_2 = now + ONE_HOUR
    release_timestamp_3 = now + 2 * ONE_HOUR
    release_timestamp_4 = now + 2 * ONE_HOUR
    rate_2 = value // ONE_HOUR // 2
    rate_3 = value // ONE_HOUR // 4
    rate_4 = 0
    tx = escrow.setupVesting(
        [staker2, staker3, staker4],
        [release_timestamp_2, release_timestamp_3, release_timestamp_4],
        [rate_2, rate_3, rate_4],
        {"from": creator},
    )

    assert abs(escrow.getUnvestedTokens(staker2) - value // 2) <= rate_2
    assert abs(escrow.getUnvestedTokens(staker3) - value // 2) <= rate_3
    assert abs(escrow.getUnvestedTokens(staker4) - value) <= rate_4
    assert escrow.stakerInfo(staker2)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_2
    assert escrow.stakerInfo(staker2)[VESTING_RELEASE_RATE_SLOT] == rate_2
    assert escrow.stakerInfo(staker3)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_3
    assert escrow.stakerInfo(staker3)[VESTING_RELEASE_RATE_SLOT] == rate_3
    assert escrow.stakerInfo(staker4)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_4
    assert escrow.stakerInfo(staker4)[VESTING_RELEASE_RATE_SLOT] == rate_4

    assert "VestingSet" in tx.events
    events = tx.events["VestingSet"]
    event = events[0]
    assert event["staker"] == staker2
    assert event["releaseTimestamp"] == release_timestamp_2
    assert event["releaseRate"] == rate_2
    event = events[1]
    assert event["staker"] == staker3
    assert event["releaseTimestamp"] == release_timestamp_3
    assert event["releaseRate"] == rate_3
    event = events[2]
    assert event["staker"] == staker4
    assert event["releaseTimestamp"] == release_timestamp_4
    assert event["releaseRate"] == rate_4

    chain.mine(timestamp=release_timestamp_2)
    assert escrow.getUnvestedTokens(staker2) == 0
    assert escrow.getUnvestedTokens(staker3) == value // 4
    assert escrow.getUnvestedTokens(staker4) == value

    chain.mine(timestamp=release_timestamp_3)
    assert escrow.getUnvestedTokens(staker2) == 0
    assert escrow.getUnvestedTokens(staker3) == 0
    assert escrow.getUnvestedTokens(staker4) == 0


def test_combined_vesting(accounts, token, worklock, escrow):
    staker = "0xcd087a44ED8EE2aCe79F497c803005Ff79A64A94"
    value = Wei("1_500_000 ether")
    
    creator = accounts[0]

    token.transfer(worklock.address, 10 * value, {"from": creator})
    worklock.depositFromWorkLock(staker, 3 * value, 0, {"from": creator})

    now = chain.time()
    release_timestamp = now + ONE_HOUR
    rate = 0

    tx = escrow.setupVesting([staker], [release_timestamp], [rate], {"from": creator})
    assert escrow.getUnvestedTokens(staker) == value
    assert escrow.stakerInfo(staker)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp
    assert escrow.stakerInfo(staker)[VESTING_RELEASE_RATE_SLOT] == rate

    assert "VestingSet" in tx.events
    event = tx.events["VestingSet"]
    assert event["staker"] == staker
    assert event["releaseTimestamp"] == release_timestamp
    assert event["releaseRate"] == rate

    chain.mine(timedelta=40 * 60)
    now = chain.time()
    assert escrow.getUnvestedTokens(staker) == value

    chain.sleep(20 * 60)
    chain.mine(timedelta=0)
    assert escrow.getUnvestedTokens(staker) == 0
