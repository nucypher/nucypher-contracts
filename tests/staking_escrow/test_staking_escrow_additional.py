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
from brownie import Contract, Wei


def test_upgrading(
    accounts,
    history,
    token,
    WorkLockForStakingEscrowMock,
    ThresholdStakingForStakingEscrowMock,
    StakingEscrow,
    StakingEscrowV2Mock,
    StakingEscrowBad,
    Dispatcher,
):
    creator = accounts[0]
    staker = accounts[1]

    # Initialize contract and staker
    worklock = creator.deploy(WorkLockForStakingEscrowMock, token.address)
    threshold_staking = creator.deploy(ThresholdStakingForStakingEscrowMock)

    # Deploy contract
    contract_library_v1 = creator.deploy(
        StakingEscrow, token.address, worklock.address, threshold_staking.address
    )
    dispatcher = creator.deploy(Dispatcher, contract_library_v1.address)

    tx = history[-1]
    assert "StateVerified" in tx.events
    event = tx.events["StateVerified"]
    assert contract_library_v1.address == event["testTarget"]
    assert event["sender"] == creator
    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract_library_v1.address == event["target"]
    assert event["sender"] == creator

    # Deploy second version of the contract
    contract_library_v2 = creator.deploy(
        StakingEscrowV2Mock, token.address, worklock.address, threshold_staking.address
    )

    contract = Contract.from_abi(
        name="StakingEscrowV2Mock", abi=contract_library_v2.abi, address=dispatcher.address
    )
    worklock.setStakingEscrow(contract.address, {"from": creator})
    threshold_staking.setStakingEscrow(contract.address, {"from": creator})

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with brownie.reverts():
        contract_library_v1.finishUpgrade(contract.address, {"from": creator})
    with brownie.reverts():
        contract_library_v1.verifyState(contract.address, {"from": creator})

    value = Wei("100_000 ether")  # TODO
    token.transfer(worklock.address, value, {"from": creator})
    worklock.depositFromWorkLock(staker, value, 0, {"from": staker})

    # Upgrade to the second version
    tx = dispatcher.upgrade(contract_library_v2.address, {"from": creator})
    # Check constructor and storage values
    assert dispatcher.target() == contract_library_v2.address
    assert contract.workLock() == worklock.address
    assert contract.valueToCheck() == 2
    # Check new ABI
    contract.setValueToCheck(3, {"from": creator})
    assert contract.valueToCheck() == 3

    assert "StateVerified" in tx.events
    event = tx.events["StateVerified"]
    assert contract_library_v2.address == event["testTarget"]
    assert event["sender"] == creator
    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract_library_v2.address == event["target"]
    assert event["sender"] == creator

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad = creator.deploy(
        StakingEscrowBad, token.address, worklock.address, threshold_staking.address
    )
    with brownie.reverts():
        dispatcher.upgrade(contract_library_v1.address, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract_library_bad.address, {"from": creator})

    # But can rollback
    tx = dispatcher.rollback({"from": creator})
    assert dispatcher.target() == contract_library_v1.address
    assert contract.workLock() == worklock.address
    # After rollback new ABI is unavailable
    with brownie.reverts():
        contract.setValueToCheck(2, {"from": creator})
    # Try to upgrade to the bad version
    with brownie.reverts():
        dispatcher.upgrade(contract_library_bad.address, {"from": creator})

    assert "StateVerified" in tx.events
    event = tx.events["StateVerified"]
    assert contract_library_v2.address == event["testTarget"]
    assert event["sender"] == creator
    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract_library_v1.address == event["target"]
    assert event["sender"] == creator


def test_measure_work(accounts, token, worklock, escrow):
    creator, staker, *everyone_else = accounts
    total_supply = token.totalSupply()

    # Measured work must be 0 and completed work must be maximum even before deposit
    assert worklock.setWorkMeasurement.call(staker, True) == 0
    assert worklock.setWorkMeasurement.call(staker, False) == 0
    assert escrow.getCompletedWork(staker) == total_supply

    # Same behaviour after depositing tokens
    value = Wei("15_000 ether")  # TODO NU(15_000, 'NU').to_units()
    token.transfer(worklock.address, value, {"from": creator})
    worklock.depositFromWorkLock(staker, value, 0, {"from": creator})
    assert worklock.setWorkMeasurement.call(staker, True) == 0
    assert worklock.setWorkMeasurement.call(staker, False) == 0
    assert escrow.getCompletedWork(staker) == total_supply


def test_snapshots(accounts, token, escrow, worklock, threshold_staking, history):
    creator = accounts[0]
    staker1 = accounts[1]
    staker2 = accounts[2]

    total_supply = token.totalSupply()

    now = history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # Staker deposits some tokens
    value = Wei("15_000 ether")  # TODO NU(15_000, 'NU').to_units()
    token.transfer(worklock.address, value, {"from": creator})
    initial_deposit = value // 100
    worklock.depositFromWorkLock(staker1, initial_deposit, 0, {"from": creator})

    now = history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # A SECOND STAKER APPEARS:
    # Staker 2 deposits some tokens. Since snapshots are disabled, no changes in history
    deposit_staker2 = 2 * initial_deposit
    worklock.depositFromWorkLock(staker2, deposit_staker2, 0, {"from": creator})
    assert deposit_staker2 == escrow.getAllTokens(staker2)
    now = history[-1].block_number
    assert escrow.totalStakedForAt(staker2, now) == 0
    assert escrow.totalStakedAt(now) == total_supply

    # Finally, the first staker withdraws some tokens
    withdrawal = 42
    escrow.withdraw(withdrawal, {"from": staker1})
    last_balance_staker1 = initial_deposit - withdrawal
    assert last_balance_staker1 == escrow.getAllTokens(staker1)
    now = history[-1].block_number
    assert escrow.totalStakedForAt(staker1, now) == 0
    assert escrow.totalStakedAt(now) == total_supply
