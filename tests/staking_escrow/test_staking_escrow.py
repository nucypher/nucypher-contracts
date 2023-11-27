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


def test_withdraw(accounts, token, worklock, threshold_staking, escrow, chain):
    creator, staker, staking_provider = accounts[0:3]

    # Deposit some tokens
    value = Web3.to_wei(
        ONE_HOUR, "ether"
    )  # Exclude rounding error  # TODO NU(ONE_HOUR, 'NU').to_units()
    token.transfer(worklock.address, 10 * value, sender=creator)
    worklock.depositFromWorkLock(staker, value + 1, 0, sender=creator)

    # Can't withdraw 0 tokens
    with ape.reverts():
        escrow.withdraw(0, sender=staker)

    # Only staker can withdraw stake
    with ape.reverts():
        escrow.withdraw(1, sender=staking_provider)

    # Withdraw
    tx = escrow.withdraw(1, sender=staker)
    assert escrow.getAllTokens(staker) == value
    assert token.balanceOf(staker) == 1
    assert token.balanceOf(escrow.address) == value

    events = escrow.Withdrawn.from_receipt(tx)
    assert events == [escrow.Withdrawn(staker=staker, value=1)]


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

    escrow.setStakingProvider(staker, staking_provider, sender=creator)

    tx = escrow.wrapAndTopUp(sender=staker)
    assert escrow.getAllTokens(staker) == 0
    assert token.balanceOf(staker) == 0
    assert token.balanceOf(escrow.address) == 0
    assert token.balanceOf(vending_machine.address) == value
    assert t_token.balanceOf(threshold_staking.address) == value
    assert t_token.balanceOf(vending_machine.address) == TOTAL_SUPPLY - value

    events = escrow.WrappedAndToppedUp.from_receipt(tx)
    assert events == [escrow.WrappedAndToppedUp(staker=staker, value=value)]

    # Wrap again but with remainder
    other_value = Web3.to_wei(15_000, "ether") + 1
    worklock.depositFromWorkLock(other_staker, other_value, 0, sender=creator)
    escrow.setStakingProvider(other_staker, other_staker, sender=creator)

    tx = escrow.wrapAndTopUp(sender=other_staker)
    expected_value = value + other_value - 1
    assert escrow.getAllTokens(other_staker) == 1
    assert token.balanceOf(other_staker) == 0
    assert token.balanceOf(escrow.address) == 1
    assert token.balanceOf(vending_machine.address) == expected_value
    assert t_token.balanceOf(threshold_staking.address) == expected_value
    assert t_token.balanceOf(vending_machine.address) == TOTAL_SUPPLY - expected_value

    events = escrow.WrappedAndToppedUp.from_receipt(tx)
    assert events == [escrow.WrappedAndToppedUp(staker=other_staker, value=other_value - 1)]
