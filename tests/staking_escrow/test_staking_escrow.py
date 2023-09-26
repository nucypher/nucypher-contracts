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
from web3 import Web3

VESTING_RELEASE_TIMESTAMP_SLOT = 9
VESTING_RELEASE_RATE_SLOT = 10
STAKING_PROVIDER_SLOT = 11
ONE_HOUR = 60 * 60
TOTAL_SUPPLY = Web3.to_wei(1_000_000_000, "ether")


def test_staking_from_worklock(project, accounts, token, worklock, escrow):
    """
    Tests for staking method: depositFromWorkLock
    """

    creator, staker1, staker2, staker3 = accounts[0:4]

    # Give WorkLock and Staker some coins
    value = Web3.to_wei(15_000, "ether")  # TODO
    token.transfer(worklock.address, 10 * value, sender=creator)

    # Can't use method not from WorkLock
    with ape.reverts():
        escrow.depositFromWorkLock(staker1, value, 0, sender=staker1)
    # Can't deposit 0 tokens
    with ape.reverts():
        escrow.depositFromWorkLock(staker1, 0, 0, sender=staker1)
    assert token.balanceOf(escrow.address) == 0

    # First deposit
    tx = worklock.depositFromWorkLock(staker1, value, 0, sender=creator)
    assert token.balanceOf(escrow.address) == value
    assert escrow.getAllTokens(staker1) == value
    assert escrow.getStakersLength() == 1
    assert escrow.stakers(0) == staker1

    # Check that all events are emitted
    events = escrow.Deposited.from_receipt(tx)
    assert events == [escrow.Deposited(staker=staker1, value=value)]

    # Deposit directly and then through WorkLock
    escrow.setStaker(staker2, value, 0, sender=staker2)
    tx = worklock.depositFromWorkLock(staker2, value, 0, sender=creator)
    assert token.balanceOf(escrow.address) == 2 * value
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.getStakersLength() == 2
    assert escrow.stakers(1) == staker2

    # Check that all events are emitted
    events = escrow.Deposited.from_receipt(tx)
    assert events == [escrow.Deposited(staker=staker2, value=value)]

    # Emulate case when staker withdraws everything and then deposits from WorkLock
    escrow.setStaker(staker3, 0, 1, sender=staker3)
    tx = worklock.depositFromWorkLock(staker3, value, 0, sender=creator)
    assert token.balanceOf(escrow.address) == 3 * value
    assert escrow.getAllTokens(staker3) == value
    assert escrow.getStakersLength() == 3
    assert escrow.stakers(2) == staker3

    # Check that all events are emitted
    events = escrow.Deposited.from_receipt(tx)
    assert events == [escrow.Deposited(staker=staker3, value=value)]


def test_slashing(accounts, token, worklock, threshold_staking, escrow):
    creator = accounts[0]
    staker = accounts[1]
    investigator = accounts[2]

    # Staker deposits some tokens
    stake = Web3.to_wei(15_000, "ether")  # TODO
    token.transfer(worklock.address, 10 * stake, sender=creator)
    worklock.depositFromWorkLock(staker, stake, 0, sender=creator)

    assert stake == escrow.getAllTokens(staker)

    reward = stake // 100
    # Can't slash directly using the escrow contract
    with ape.reverts():
        escrow.slashStaker(staker, stake, investigator, reward, sender=creator)
    # Penalty must be greater than zero
    with ape.reverts():
        threshold_staking.slashStaker(staker, 0, investigator, 0, sender=creator)

    # Slash the whole stake
    tx = threshold_staking.slashStaker(staker, 2 * stake, investigator, reward, sender=creator)
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(investigator) == reward

    events = escrow.Slashed.from_receipt(tx)
    assert events == [
        escrow.Slashed(staker=staker, penalty=stake, investigator=investigator, reward=reward)
    ]

    # Slash small part
    worklock.depositFromWorkLock(staker, stake, 0, sender=creator)
    amount_to_slash = stake // 10
    tx = threshold_staking.slashStaker(
        staker, amount_to_slash, investigator, 2 * amount_to_slash, sender=creator
    )
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == stake - amount_to_slash
    assert token.balanceOf(investigator) == reward + amount_to_slash

    events = escrow.Slashed.from_receipt(tx)
    assert events == [
        escrow.Slashed(
            staker=staker,
            penalty=amount_to_slash,
            investigator=investigator,
            reward=amount_to_slash,
        )
    ]

    # Slash without reward
    tx = threshold_staking.slashStaker(staker, amount_to_slash, investigator, 0, sender=creator)
    # Staker has no more stake
    assert escrow.getAllTokens(staker) == stake - 2 * amount_to_slash
    assert token.balanceOf(investigator) == reward + amount_to_slash

    events = escrow.Slashed.from_receipt(tx)
    assert events == [
        escrow.Slashed(staker=staker, penalty=amount_to_slash, investigator=investigator, reward=0)
    ]


def test_request_merge(accounts, threshold_staking, escrow):
    creator, staker1, staker2, staking_provider_1, staking_provider_2 = accounts[0:5]

    # Can't request merge directly
    with ape.reverts():
        escrow.requestMerge(staker1, staking_provider_1, sender=creator)

    # Requesting merge for non-existent staker will return zero
    tx = threshold_staking.requestMerge(staker1, staking_provider_1, sender=creator)
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0

    assert tx.events == [escrow.MergeRequested(staker=staker1, stakingProvider=staking_provider_1)]

    # Request can be made several times
    tx = threshold_staking.requestMerge(staker1, staking_provider_1, sender=creator)
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0
    assert tx.events == []

    # Can change provider if old provider has no delegated stake
    tx = threshold_staking.requestMerge(staker1, staker1, sender=creator)
    assert escrow.getAllTokens(staker1) == 0
    assert escrow.stakerInfo(staker1)[STAKING_PROVIDER_SLOT] == staker1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 0

    assert tx.events == [escrow.MergeRequested(staker=staker1, stakingProvider=staker1)]

    # Requesting merge for existent staker will return stake
    value = 1000
    escrow.setStaker(staker2, value, 0, sender=creator)
    tx = threshold_staking.requestMerge(staker2, staking_provider_2, sender=creator)
    assert escrow.getAllTokens(staker2) == value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == value

    assert tx.events == [escrow.MergeRequested(staker=staker2, stakingProvider=staking_provider_2)]

    # Request can be made several times
    threshold_staking.requestMerge(staker2, staking_provider_2, sender=creator)
    assert escrow.getAllTokens(staker2) == value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == value

    escrow.setStaker(staker2, 2 * value, 0, sender=creator)
    tx = threshold_staking.requestMerge(staker2, staking_provider_2, sender=creator)
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_2
    assert threshold_staking.stakingProviders(staking_provider_2)[0] == 2 * value
    assert tx.events == []

    # Request can be done only with the same provider when NU is staked
    with ape.reverts():
        threshold_staking.requestMerge(staker2, staking_provider_1, sender=creator)

    # Unstake NU and try again
    threshold_staking.setStakedNu(staking_provider_2, 0, sender=creator)
    tx = threshold_staking.requestMerge(staker2, staking_provider_1, sender=creator)
    assert escrow.getAllTokens(staker2) == 2 * value
    assert escrow.stakerInfo(staker2)[STAKING_PROVIDER_SLOT] == staking_provider_1
    assert threshold_staking.stakingProviders(staking_provider_1)[0] == 2 * value

    assert tx.events == [escrow.MergeRequested(staker=staker2, stakingProvider=staking_provider_1)]


def test_withdraw(accounts, token, worklock, threshold_staking, escrow, chain):
    creator, staker, staking_provider = accounts[0:3]

    # Deposit some tokens
    value = Web3.to_wei(
        ONE_HOUR, "ether"
    )  # Exclude rounding error  # TODO NU(ONE_HOUR, 'NU').to_units()
    token.transfer(worklock.address, 10 * value, sender=creator)
    worklock.depositFromWorkLock(staker, value + 1, 0, sender=creator)

    # Withdraw without requesting merge
    tx = escrow.withdraw(1, sender=staker)
    assert escrow.getAllTokens(staker) == value
    assert token.balanceOf(staker) == 1
    assert token.balanceOf(escrow.address) == value

    events = escrow.Withdrawn.from_receipt(tx)
    assert events == [escrow.Withdrawn(staker=staker, value=1)]

    threshold_staking.requestMerge(staker, staking_provider, sender=creator)

    # Can't withdraw because everything is staked
    with ape.reverts():
        escrow.withdraw(1, sender=staker)

    # Set vesting for the staker
    threshold_staking.setStakedNu(staking_provider, value // 2, sender=creator)
    now = chain.pending_timestamp
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR
    escrow.setupVesting([staker], [release_timestamp], [rate], sender=creator)

    # Vesting parameters prevent from withdrawing
    with ape.reverts():
        escrow.withdraw(1, sender=staker)

    # Wait some time
    chain.pending_timestamp += 40 * 60
    released = value - escrow.getUnvestedTokens(staker)

    # Can't withdraw more than released
    to_withdraw = released
    with ape.reverts():
        escrow.withdraw(to_withdraw + rate + 1, sender=staker)

    tx = escrow.withdraw(to_withdraw, sender=staker)
    assert escrow.getAllTokens(staker) == value - to_withdraw
    assert token.balanceOf(staker) == to_withdraw + 1
    assert token.balanceOf(escrow.address) == value - to_withdraw

    events = escrow.Withdrawn.from_receipt(tx)
    assert events == [escrow.Withdrawn(staker=staker, value=to_withdraw)]

    # Can't withdraw more than unstaked
    chain.pending_timestamp += 30 * 60
    unstaked = value // 2 - to_withdraw
    with ape.reverts():
        escrow.withdraw(unstaked + 1, sender=staker)

    # Can't withdraw 0 tokens
    with ape.reverts():
        escrow.withdraw(0, sender=staker)

    # Only staker can withdraw stake
    with ape.reverts():
        escrow.withdraw(1, sender=staking_provider)

    tx = escrow.withdraw(unstaked, sender=staker)
    assert escrow.getAllTokens(staker) == value // 2
    assert token.balanceOf(staker) == value // 2 + 1
    assert token.balanceOf(escrow.address) == value // 2

    events = escrow.Withdrawn.from_receipt(tx)
    assert events == [escrow.Withdrawn(staker=staker, value=unstaked)]

    # Now unstake and withdraw everything
    threshold_staking.setStakedNu(staking_provider, 0, sender=creator)
    tx = escrow.withdraw(value // 2, sender=staker)
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(staker) == value + 1
    assert token.balanceOf(escrow.address) == 0

    events = escrow.Withdrawn.from_receipt(tx)
    assert events == [escrow.Withdrawn(staker=staker, value=value // 2)]


def test_vesting(accounts, token, worklock, escrow, chain):
    creator, staker1, staker2, staker3, staker4 = accounts[0:5]

    value = Web3.to_wei(15_000, "ether")  # TODO
    token.transfer(worklock.address, 10 * value, sender=creator)
    worklock.depositFromWorkLock(staker1, value, 0, sender=creator)

    now = chain.pending_timestamp
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR

    # Only owner can set vesting parameters
    with ape.reverts():
        escrow.setupVesting([staker1], [release_timestamp], [rate], sender=staker1)

    # All input arrays must have same number of values
    with ape.reverts():
        escrow.setupVesting(
            [staker1, staker2], [release_timestamp, release_timestamp], [rate], sender=creator
        )
    with ape.reverts():
        escrow.setupVesting([staker1, staker2], [release_timestamp], [rate, rate], sender=creator)
    with ape.reverts():
        escrow.setupVesting(
            [staker1], [release_timestamp, release_timestamp], [rate, rate], sender=creator
        )

    # At least some amount of tokens must be locked after setting parameters
    with ape.reverts():
        escrow.setupVesting([staker1], [now], [rate], sender=creator)
    with ape.reverts():
        escrow.setupVesting(
            [staker1, staker2],
            [release_timestamp, release_timestamp],
            [rate, rate],
            sender=creator,
        )

    tx = escrow.setupVesting([staker1], [release_timestamp], [rate], sender=creator)
    assert escrow.getUnvestedTokens(staker1) == value
    assert escrow.stakerInfo(staker1)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp
    assert escrow.stakerInfo(staker1)[VESTING_RELEASE_RATE_SLOT] == rate

    assert tx.events == [
        escrow.VestingSet(staker=staker1, releaseTimestamp=release_timestamp, releaseRate=rate)
    ]

    chain.pending_timestamp += 40 * 60
    now = chain.pending_timestamp - 1
    vested = (release_timestamp - now) * rate
    assert escrow.getUnvestedTokens(staker1) == vested

    chain.pending_timestamp += 20 * 60
    assert escrow.getUnvestedTokens(staker1) == 0

    # Can't set vesting again even after unlocking
    with ape.reverts():
        escrow.setupVesting([staker1], [release_timestamp], [rate], sender=creator)

    # Try again with three other stakers
    value = Web3.to_wei(
        ONE_HOUR, "ether"
    )  # Exclude rounding error  # TODO NU(ONE_HOUR, 'NU').to_units()
    worklock.depositFromWorkLock(staker2, value, 0, sender=creator)
    worklock.depositFromWorkLock(staker3, value, 0, sender=creator)
    worklock.depositFromWorkLock(staker4, value, 0, sender=creator)

    now = chain.pending_timestamp
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
        sender=creator,
    )

    assert escrow.getUnvestedTokens(staker2) == value // 2
    assert escrow.getUnvestedTokens(staker3) == value // 2
    assert escrow.getUnvestedTokens(staker4) == value
    assert escrow.stakerInfo(staker2)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_2
    assert escrow.stakerInfo(staker2)[VESTING_RELEASE_RATE_SLOT] == rate_2
    assert escrow.stakerInfo(staker3)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_3
    assert escrow.stakerInfo(staker3)[VESTING_RELEASE_RATE_SLOT] == rate_3
    assert escrow.stakerInfo(staker4)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_4
    assert escrow.stakerInfo(staker4)[VESTING_RELEASE_RATE_SLOT] == rate_4

    assert tx.events == [
        escrow.VestingSet(staker=staker2, releaseTimestamp=release_timestamp_2, releaseRate=rate_2),
        escrow.VestingSet(staker=staker3, releaseTimestamp=release_timestamp_3, releaseRate=rate_3),
        escrow.VestingSet(staker=staker4, releaseTimestamp=release_timestamp_4, releaseRate=rate_4),
    ]

    chain.pending_timestamp += ONE_HOUR
    assert escrow.getUnvestedTokens(staker2) == 0
    assert escrow.getUnvestedTokens(staker3) == value // 4
    assert escrow.getUnvestedTokens(staker4) == value

    chain.pending_timestamp += ONE_HOUR
    assert escrow.getUnvestedTokens(staker2) == 0
    assert escrow.getUnvestedTokens(staker3) == 0
    assert escrow.getUnvestedTokens(staker4) == 0


def test_combined_vesting(accounts, token, worklock, escrow, chain):
    staker = "0xcd087a44ED8EE2aCe79F497c803005Ff79A64A94"
    value = Web3.to_wei(1_500_000, "ether")  # TODO

    creator = accounts[0]

    token.transfer(worklock.address, 10 * value, sender=creator)
    worklock.depositFromWorkLock(staker, 3 * value, 0, sender=creator)

    now = chain.pending_timestamp
    release_timestamp = now + ONE_HOUR
    rate = 0

    tx = escrow.setupVesting([staker], [release_timestamp], [rate], sender=creator)
    assert escrow.getUnvestedTokens(staker) == value
    assert escrow.stakerInfo(staker)[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp
    assert escrow.stakerInfo(staker)[VESTING_RELEASE_RATE_SLOT] == rate

    assert tx.events == [
        escrow.VestingSet(staker=staker, releaseTimestamp=release_timestamp, releaseRate=rate)
    ]

    chain.pending_timestamp += 40 * 60
    now = chain.pending_timestamp - 1
    assert escrow.getUnvestedTokens(staker) == value

    chain.pending_timestamp += 20 * 60
    assert escrow.getUnvestedTokens(staker) == 0


def test_wrap(
    accounts, token, worklock, threshold_staking, escrow, vending_machine, t_token, chain
):
    creator, staker, staking_provider, other_staker = accounts[0:4]

    with ape.reverts():
        escrow.wrapAndTopUp(sender=staker)

    # Deposit some tokens
    value = Web3.to_wei(15_000, "ether")
    token.transfer(worklock.address, 10 * value, sender=creator)
    worklock.depositFromWorkLock(staker, value, 0, sender=creator)

    # Can't wrap without requesting merge
    with ape.reverts():
        escrow.wrapAndTopUp(sender=staker)

    threshold_staking.requestMerge(staker, staking_provider, sender=creator)

    with ape.reverts():
        escrow.wrapAndTopUp(sender=staker)

    threshold_staking.setStakedNu(staking_provider, 0, sender=creator)
    now = chain.pending_timestamp
    release_timestamp = now + ONE_HOUR
    rate = value // ONE_HOUR
    escrow.setupVesting([staker], [release_timestamp], [rate], sender=creator)

    with ape.reverts():
        escrow.wrapAndTopUp(sender=staker)

    chain.pending_timestamp += ONE_HOUR

    tx = escrow.wrapAndTopUp(sender=staker)
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(staker) == 0
    assert token.balanceOf(escrow.address) == 0
    assert token.balanceOf(vending_machine.address) == value
    assert t_token.balanceOf(threshold_staking.address) == value
    assert t_token.balanceOf(vending_machine.address) == TOTAL_SUPPLY - value

    events = escrow.WrappedAndTopedUp.from_receipt(tx)
    assert events == [escrow.WrappedAndTopedUp(staker=staker, value=value)]

    # Wrap again but with remainder
    other_value = Web3.to_wei(15_000, "ether") + 1
    worklock.depositFromWorkLock(other_staker, other_value, 0, sender=creator)
    threshold_staking.requestMerge(other_staker, other_staker, sender=creator)
    threshold_staking.setStakedNu(other_staker, 0, sender=creator)

    tx = escrow.wrapAndTopUp(sender=other_staker)
    expected_value = value + other_value - 1
    assert escrow.getAllTokens(other_staker) == 1
    assert token.balanceOf(other_staker) == 0
    assert token.balanceOf(escrow.address) == 1
    assert token.balanceOf(vending_machine.address) == expected_value
    assert t_token.balanceOf(threshold_staking.address) == expected_value
    assert t_token.balanceOf(vending_machine.address) == TOTAL_SUPPLY - expected_value

    events = escrow.WrappedAndTopedUp.from_receipt(tx)
    assert events == [escrow.WrappedAndTopedUp(staker=other_staker, value=other_value - 1)]
