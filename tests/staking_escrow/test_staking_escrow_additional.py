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


def test_upgrading(accounts, token, project):
    creator = accounts[0]
    staker = accounts[1]

    # Initialize contract and staker
    worklock = creator.deploy(project.WorkLockForStakingEscrowMock, token.address)
    threshold_staking = creator.deploy(project.ThresholdStakingForStakingEscrowMock)

    # Deploy contract
    contract_library_v1 = creator.deploy(
        project.StakingEscrow, token.address, worklock.address, threshold_staking.address
    )
    dispatcher = creator.deploy(project.Dispatcher, contract_library_v1.address)

    tx = creator.history[-1]
    events = dispatcher.StateVerified.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract_library_v1.address == event["testTarget"]
    assert event["sender"] == creator
    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract_library_v1.address == event["target"]
    assert event["sender"] == creator

    # Deploy second version of the contract
    contract_library_v2 = creator.deploy(
        project.StakingEscrowV2Mock, token.address, worklock.address, threshold_staking.address
    )

    contract = project.StakingEscrowV2Mock.at(dispatcher.address)
    worklock.setStakingEscrow(contract.address, sender=creator)
    threshold_staking.setStakingEscrow(contract.address, sender=creator)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with ape.reverts():
        contract_library_v1.finishUpgrade(contract.address, sender=creator)
    with ape.reverts():
        contract_library_v1.verifyState(contract.address, sender=creator)

    value = Web3.to_wei(100_000, "ether")  # TODO
    token.transfer(worklock.address, value, sender=creator)
    worklock.depositFromWorkLock(staker, value, 0, sender=staker)

    # Upgrade to the second version
    tx = dispatcher.upgrade(contract_library_v2.address, sender=creator)
    # Check constructor and storage values
    assert dispatcher.target() == contract_library_v2.address
    assert contract.workLock() == worklock.address
    assert contract.valueToCheck() == 2
    # Check new ABI
    contract.setValueToCheck(3, sender=creator)
    assert contract.valueToCheck() == 3

    events = dispatcher.StateVerified.from_receipt(tx)
    assert len(events) == 2
    event = events[0]
    assert contract_library_v2.address == event["testTarget"]
    assert event["sender"] == creator
    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract_library_v2.address == event["target"]
    assert event["sender"] == creator

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad = creator.deploy(
        project.StakingEscrowBad, token.address, worklock.address, threshold_staking.address
    )
    with ape.reverts():
        dispatcher.upgrade(contract_library_v1.address, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract_library_bad.address, sender=creator)

    # But can rollback
    tx = dispatcher.rollback(sender=creator)
    assert dispatcher.target() == contract_library_v1.address
    assert contract.workLock() == worklock.address
    # After rollback new ABI is unavailable
    with ape.reverts():
        contract.setValueToCheck(2, sender=creator)
    # Try to upgrade to the bad version
    with ape.reverts():
        dispatcher.upgrade(contract_library_bad.address, sender=creator)

    events = dispatcher.StateVerified.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract_library_v2.address == event["testTarget"]
    assert event["sender"] == creator
    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract_library_v1.address == event["target"]
    assert event["sender"] == creator


def test_measure_work(accounts, token, worklock, escrow):
    creator, staker, *everyone_else = accounts[0:]
    total_supply = token.totalSupply()

    # Measured work must be 0 and completed work must be maximum even before deposit
    assert worklock.setWorkMeasurement.call(staker, True) == 0
    assert worklock.setWorkMeasurement.call(staker, False) == 0
    assert escrow.getCompletedWork(staker) == total_supply

    # Same behaviour after depositing tokens
    value = Web3.to_wei(15_000, "ether")  # TODO NU(15_000, 'NU').to_units()
    token.transfer(worklock.address, value, sender=creator)
    worklock.depositFromWorkLock(staker, value, 0, sender=creator)
    assert worklock.setWorkMeasurement.call(staker, True) == 0
    assert worklock.setWorkMeasurement.call(staker, False) == 0
    assert escrow.getCompletedWork(staker) == total_supply


def test_snapshots(accounts, token, escrow, worklock):
    creator = accounts[0]
    staker1 = accounts[1]
    staker2 = accounts[2]

    total_supply = token.totalSupply()

    now = creator.history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # Staker deposits some tokens
    value = Web3.to_wei(15_000, "ether")  # TODO NU(15_000, 'NU').to_units()
    token.transfer(worklock.address, value, sender=creator)
    initial_deposit = value // 100
    worklock.depositFromWorkLock(staker1, initial_deposit, 0, sender=creator)

    now = creator.history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # A SECOND STAKER APPEARS:
    # Staker 2 deposits some tokens. Since snapshots are disabled, no changes in history
    deposit_staker2 = 2 * initial_deposit
    worklock.depositFromWorkLock(staker2, deposit_staker2, 0, sender=creator)
    assert deposit_staker2 == escrow.getAllTokens(staker2)
    now = creator.history[-1].block_number
    assert escrow.totalStakedForAt(staker2, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # Finally, the first staker withdraws some tokens
    withdrawal = 42
    escrow.withdraw(withdrawal, sender=staker1)
    last_balance_staker1 = initial_deposit - withdrawal
    assert last_balance_staker1 == escrow.getAllTokens(staker1)
    now = staker1.history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply
