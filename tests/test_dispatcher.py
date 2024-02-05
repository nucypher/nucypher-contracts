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
import pytest
from ape.utils import ZERO_ADDRESS


def test_dispatcher(project, accounts):
    creator = accounts[0]
    account = accounts[1]

    # Try to deploy broken libraries and dispatcher for them
    contract0_bad_lib = creator.deploy(project.BadDispatcherStorage)
    contract2_bad_verify_state_lib = creator.deploy(project.ContractV2BadVerifyState)
    with ape.reverts():
        creator.deploy(project.Dispatcher, contract0_bad_lib.address)
    with ape.reverts():
        creator.deploy(project.Dispatcher, contract2_bad_verify_state_lib.address)

    # Deploy contracts and dispatcher for them
    contract1_lib = creator.deploy(project.ContractV1, 1)
    contract2_lib = creator.deploy(project.ContractV2, 1)
    contract3_lib = creator.deploy(project.ContractV3, 2)
    contract4_lib = creator.deploy(project.ContractV4, 3)
    contract2_bad_storage_lib = creator.deploy(project.ContractV2BadStorage)
    dispatcher = creator.deploy(project.Dispatcher, contract1_lib.address)
    assert contract1_lib.address == dispatcher.target()
    assert dispatcher.implementation() == contract1_lib.address
    assert dispatcher.proxyType() == 2

    tx = creator.history[-1]
    events = dispatcher.Upgraded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert ZERO_ADDRESS == event["from"]
    assert contract1_lib.address == event["to"]
    assert creator == event["owner"]

    events = dispatcher.StateVerified.from_receipt(tx)
    assert events == [dispatcher.StateVerified(testTarget=contract1_lib.address, sender=creator)]

    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert events == [dispatcher.UpgradeFinished(target=contract1_lib.address, sender=creator)]

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = project.ContractV1.at(dispatcher.address)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with ape.reverts():
        dispatcher.verifyState(contract1_lib.address, sender=creator)
    with ape.reverts():
        contract1_lib.finishUpgrade(contract1_lib.address, sender=creator)
    with ape.reverts():
        contract1_lib.verifyState(contract1_lib.address, sender=creator)

    # Check values and methods before upgrade
    assert 1 == contract_instance.storageValue()
    assert 10 == contract_instance.returnValue()
    contract_instance.setStorageValue(5, sender=creator)
    assert 5 == contract_instance.storageValue()
    contract_instance.pushArrayValue(12, sender=creator)
    assert 1 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    contract_instance.pushArrayValue(232, sender=creator)
    assert 2 == contract_instance.getArrayValueLength()
    assert 232 == contract_instance.arrayValues(1)
    contract_instance.setMappingValue(14, 41, sender=creator)
    assert 41 == contract_instance.mappingValues(14)
    contract_instance.pushStructureValue1(3, sender=creator)
    assert 3 == contract_instance.arrayStructures(0)
    contract_instance.pushStructureArrayValue1(0, 11, sender=creator)
    contract_instance.pushStructureArrayValue1(0, 111, sender=creator)
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    contract_instance.pushStructureValue2(4, sender=creator)
    assert 4 == contract_instance.mappingStructures(0)
    contract_instance.pushStructureArrayValue2(0, 12, sender=creator)
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    contract_instance.setDynamicallySizedValue("Hola", sender=creator)
    assert "Hola" == contract_instance.dynamicallySizedValue()

    # Only owner can change target address for the dispatcher
    with ape.reverts():
        dispatcher.upgrade(contract2_lib.address, sender=account)

    # Can't upgrade to the bad version
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, sender=creator)

    # Upgrade contract
    assert contract1_lib.address == dispatcher.target()
    tx = dispatcher.upgrade(contract2_lib.address, sender=creator)
    assert contract2_lib.address == dispatcher.target()

    tx = creator.history[-1]
    events = dispatcher.Upgraded.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract1_lib.address == event["from"]
    assert contract2_lib.address == event["to"]
    assert creator == event["owner"]

    events = dispatcher.StateVerified.from_receipt(tx)
    assert events == [
        dispatcher.StateVerified(testTarget=contract2_lib.address, sender=creator),
        dispatcher.StateVerified(testTarget=contract2_lib.address, sender=creator),
    ]

    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert events == [dispatcher.UpgradeFinished(target=contract2_lib.address, sender=creator)]

    # Check values and methods after upgrade
    assert 20 == contract_instance.returnValue()
    assert 5 == contract_instance.storageValue()
    contract_instance.setStorageValue(5, sender=creator)
    assert 10 == contract_instance.storageValue()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    contract_instance.setMappingValue(13, 31, sender=creator)
    assert 41 == contract_instance.mappingValues(14)
    assert 31 == contract_instance.mappingValues(13)
    contract_instance.pushStructureValue1(4, sender=creator)
    assert 3 == contract_instance.arrayStructures(0)
    assert 4 == contract_instance.arrayStructures(1)
    contract_instance.pushStructureArrayValue1(0, 12, sender=creator)
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    assert 12 == contract_instance.getStructureArrayValue1(0, 2)
    contract_instance.pushStructureValue2(5, sender=creator)
    assert 4 == contract_instance.mappingStructures(0)
    assert 5 == contract_instance.mappingStructures(1)
    contract_instance.pushStructureArrayValue2(0, 13, sender=creator)
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    assert 13 == contract_instance.getStructureArrayValue2(0, 1)
    assert "Hola" == contract_instance.dynamicallySizedValue()
    contract_instance.setDynamicallySizedValue("Hello", sender=creator)
    assert "Hello" == contract_instance.dynamicallySizedValue()

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = project.ContractV2.at(dispatcher.address)

    # Check new method and finishUpgrade method
    assert 1 == contract_instance.storageValueToCheck()
    contract_instance.setStructureValueToCheck2(0, 55, sender=creator)
    assert [4, 55] == contract_instance.mappingStructures(0)

    # Can't downgrade to the first version due to new storage variables
    with ape.reverts():
        dispatcher.upgrade(contract1_lib.address, sender=creator)

    # And can't upgrade to the bad version
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, sender=creator)
    assert contract2_lib.address == dispatcher.target()

    # Only owner can rollback
    with ape.reverts():
        dispatcher.rollback(sender=account)

    # Can rollback to the first version
    tx = dispatcher.rollback(sender=creator)
    assert contract1_lib.address == dispatcher.target()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    assert 1 == contract_instance.storageValue()
    contract_instance.setStorageValue(5, sender=creator)
    assert 5 == contract_instance.storageValue()

    events = dispatcher.RolledBack.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert contract2_lib.address == event["from"]
    assert contract1_lib.address == event["to"]
    assert creator == event["owner"]

    events = dispatcher.StateVerified.from_receipt(tx)
    assert events == [dispatcher.StateVerified(testTarget=contract2_lib.address, sender=creator)]

    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert events == [dispatcher.UpgradeFinished(target=contract1_lib.address, sender=creator)]

    # Can't upgrade to the bad version
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, sender=creator)
    assert contract1_lib.address == dispatcher.target()

    # Create Event
    contract_instance = project.ContractV1.at(dispatcher.address)
    tx = contract_instance.createEvent(33, sender=creator)
    assert tx.events == [contract_instance.EventV1(value=33)]

    # Upgrade to the version 3
    tx1 = dispatcher.upgrade(contract2_lib.address, sender=creator)
    tx2 = dispatcher.upgrade(contract3_lib.address, sender=creator)

    events = dispatcher.Upgraded.from_receipt(tx1)
    assert len(events) == 1
    event = events[0]
    assert contract1_lib.address == event["from"]
    assert contract2_lib.address == event["to"]
    assert creator == event["owner"]

    events = dispatcher.Upgraded.from_receipt(tx2)
    assert len(events) == 1
    event = events[0]
    assert contract2_lib.address == event["from"]
    assert contract3_lib.address == event["to"]
    assert creator == event["owner"]

    events = dispatcher.StateVerified.from_receipt(tx1)
    assert events == [
        dispatcher.StateVerified(testTarget=contract2_lib.address, sender=creator),
        dispatcher.StateVerified(testTarget=contract2_lib.address, sender=creator),
    ]

    events = dispatcher.StateVerified.from_receipt(tx2)
    assert events == [
        dispatcher.StateVerified(testTarget=contract3_lib.address, sender=creator),
        dispatcher.StateVerified(testTarget=contract3_lib.address, sender=creator),
    ]

    events = dispatcher.UpgradeFinished.from_receipt(tx1)
    assert events == [dispatcher.UpgradeFinished(target=contract2_lib.address, sender=creator)]

    events = dispatcher.UpgradeFinished.from_receipt(tx2)
    assert events == [dispatcher.UpgradeFinished(target=contract3_lib.address, sender=creator)]

    contract_instance = project.ContractV3.at(dispatcher.address)
    assert contract3_lib.address == dispatcher.target()
    assert 20 == contract_instance.returnValue()
    assert 5 == contract_instance.storageValue()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    assert 41 == contract_instance.mappingValues(14)
    assert 31 == contract_instance.mappingValues(13)
    assert 3 == contract_instance.arrayStructures(0)
    assert 4 == contract_instance.arrayStructures(1)
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    assert 12 == contract_instance.getStructureArrayValue1(0, 2)
    assert [4, 55] == contract_instance.mappingStructures(0)
    assert [5, 0] == contract_instance.mappingStructures(1)
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    assert 13 == contract_instance.getStructureArrayValue2(0, 1)
    assert 2 == contract_instance.storageValueToCheck()
    assert "Hello" == contract_instance.dynamicallySizedValue()
    contract_instance.setAnotherStorageValue(77, sender=creator)
    assert 77 == contract_instance.anotherStorageValue()

    # Create and check events
    tx = contract_instance.createEvent(22, sender=creator)
    assert tx.events == [contract_instance.EventV2(value=22)]

    # Check upgrading to the contract with explicit storage slots
    tx = dispatcher.upgrade(contract4_lib.address, sender=creator)
    contract_instance = project.ContractV4.at(dispatcher.address)
    assert contract4_lib.address == dispatcher.target()
    assert 30 == contract_instance.returnValue()
    assert 5 == contract_instance.storageValue()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    assert 41 == contract_instance.mappingValues(14)
    assert 31 == contract_instance.mappingValues(13)
    assert 3 == contract_instance.arrayStructures(0)
    assert 4 == contract_instance.arrayStructures(1)
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    assert 12 == contract_instance.getStructureArrayValue1(0, 2)
    assert [4, 55] == contract_instance.mappingStructures(0)
    assert [5, 0] == contract_instance.mappingStructures(1)
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    assert 13 == contract_instance.getStructureArrayValue2(0, 1)
    assert 3 == contract_instance.storageValueToCheck()
    assert "Hello" == contract_instance.dynamicallySizedValue()
    assert 77 == contract_instance.anotherStorageValue()

    events = dispatcher.StateVerified.from_receipt(tx)
    assert events == [
        dispatcher.StateVerified(testTarget=contract4_lib.address, sender=creator),
        dispatcher.StateVerified(testTarget=contract4_lib.address, sender=creator),
    ]

    events = dispatcher.UpgradeFinished.from_receipt(tx)
    assert events == [dispatcher.UpgradeFinished(target=contract4_lib.address, sender=creator)]

    # Upgrade to the previous version - check that new `verifyState` can handle old contract
    tx = dispatcher.upgrade(contract3_lib.address, sender=creator)
    assert contract3_lib.address == dispatcher.target()
    assert 20 == contract_instance.returnValue()
    assert 5 == contract_instance.storageValue()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    assert 41 == contract_instance.mappingValues(14)
    assert 31 == contract_instance.mappingValues(13)
    assert 3 == contract_instance.arrayStructures(0)
    assert 4 == contract_instance.arrayStructures(1)
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    assert 12 == contract_instance.getStructureArrayValue1(0, 2)
    assert [4, 55] == contract_instance.mappingStructures(0)
    assert [5, 0] == contract_instance.mappingStructures(1)
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    assert 13 == contract_instance.getStructureArrayValue2(0, 1)
    assert 2 == contract_instance.storageValueToCheck()
    assert "Hello" == contract_instance.dynamicallySizedValue()
    assert 77 == contract_instance.anotherStorageValue()

    events = dispatcher.StateVerified.from_receipt(tx)
    assert events == [
        dispatcher.StateVerified(testTarget=contract3_lib.address, sender=creator),
        dispatcher.StateVerified(testTarget=contract3_lib.address, sender=creator),
    ]


def test_selfdestruct(project, accounts):
    creator = accounts[0]
    account = accounts[1]

    # Deploy contract and destroy it
    contract1_lib = creator.deploy(project.Destroyable, 22)
    assert 22 == contract1_lib.constructorValue()
    contract1_lib.destroy(sender=creator)
    with pytest.raises(ape.exceptions.ContractNotFoundError):
        contract1_lib.constructorValue()

    # Can't create dispatcher using address without contract
    with ape.reverts():
        creator.deploy(project.Dispatcher, ZERO_ADDRESS)
    with ape.reverts():
        creator.deploy(project.Dispatcher, account)
    with ape.reverts():
        creator.deploy(project.Dispatcher, contract1_lib.address)

    # Deploy contract again with a dispatcher targeting it
    contract2_lib = creator.deploy(project.Destroyable, 23)
    dispatcher = creator.deploy(project.Dispatcher, contract2_lib.address)
    assert contract2_lib.address == dispatcher.target()

    contract_instance = project.Destroyable.at(dispatcher.address)
    contract_instance.setFunctionValue(34, sender=accounts[0])
    assert 23 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Can't upgrade to an address without contract
    with ape.reverts():
        dispatcher.upgrade(ZERO_ADDRESS, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(account, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract1_lib.address, sender=creator)

    # Destroy library
    contract2_lib.destroy(sender=creator)
    # Dispatcher must determine that there is no contract
    with ape.reverts():
        contract_instance.constructorValue()

    # Can't upgrade to an address without contract
    with ape.reverts():
        dispatcher.upgrade(ZERO_ADDRESS, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(account, sender=creator)
    with ape.reverts():
        dispatcher.upgrade(contract1_lib.address, sender=creator)

    # Deploy the same contract again and upgrade to this contract
    contract3_lib = creator.deploy(project.Destroyable, 24)
    dispatcher.upgrade(contract3_lib.address, sender=creator)
    assert 24 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Can't rollback because the previous version is destroyed
    with ape.reverts():
        dispatcher.rollback(sender=account)

    # Destroy again
    contract3_lib.destroy(sender=creator)
    with ape.reverts():
        contract_instance.constructorValue()

    # Still can't rollback because the previous version is destroyed
    with ape.reverts():
        dispatcher.rollback(sender=account)

    # Deploy the same contract twice and upgrade to the latest contract
    contract4_lib = creator.deploy(project.Destroyable, 25)
    contract5_lib = creator.deploy(project.Destroyable, 26)
    dispatcher.upgrade(contract4_lib.address, sender=creator)
    dispatcher.upgrade(contract5_lib.address, sender=creator)
    assert 26 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Destroy the previous version of the contract and try to rollback again
    contract4_lib.destroy(sender=creator)
    with ape.reverts():
        dispatcher.rollback(sender=account)

    # Deploy the same contract again and upgrade
    contract6_lib = creator.deploy(project.Destroyable, 27)
    dispatcher.upgrade(contract6_lib.address, sender=creator)
    assert 27 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Destroy the current version of the contract
    contract6_lib.destroy(sender=creator)
    # Now rollback must work, the previous version is fine
    dispatcher.rollback(sender=creator)
    assert 26 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()


def test_receive_fallback(project, accounts):
    creator = accounts[0]
    # Deploy first contract
    no_fallback_lib = project.NoFallback.deploy(sender=creator)
    dispatcher = project.Dispatcher.deploy(no_fallback_lib.address, sender=creator)
    contract_instance = project.NoFallback.at(dispatcher.address)

    # Can't transfer ETH to this version of contract
    value = 10000
    with ape.reverts():
        creator.transfer(contract_instance.address, value)
    assert contract_instance.balance == 0

    # Upgrade to other contract
    receive_lib = project.OnlyReceive.deploy(sender=creator)
    dispatcher.upgrade(receive_lib.address, sender=creator)
    contract_instance = project.OnlyReceive.at(dispatcher.address)

    # Transfer ETH and check which function was executed
    creator.transfer(contract_instance.address, value)
    assert contract_instance.value() == value
    assert contract_instance.receiveRequests() == 1
    assert contract_instance.balance == value

    # Upgrade to other contract and transfer ETH again
    receive_fallback_lib = project.ReceiveFallback.deploy(sender=creator)
    dispatcher.upgrade(receive_fallback_lib.address, sender=creator)
    contract_instance = project.ReceiveFallback.at(dispatcher.address)

    creator.transfer(contract_instance.address, value)
    assert contract_instance.receiveRequests() == 2
    assert contract_instance.value() == 2 * value
    assert contract_instance.fallbackRequests() == 0
    assert contract_instance.balance == 2 * value
