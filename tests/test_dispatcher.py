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
import pytest
from brownie import Contract

NULL_ADDRESS = brownie.convert.to_address("0x" + "0" * 40)  # TODO move to some test constants


def test_dispatcher(
    Dispatcher,
    BadDispatcherStorage,
    ContractV1,
    ContractV2,
    ContractV3,
    ContractV4,
    ContractV2BadVerifyState,
    ContractV2BadStorage,
    accounts,
    history,
):
    creator = accounts[0]
    account = accounts[1]

    # Try to deploy broken libraries and dispatcher for them
    contract0_bad_lib = creator.deploy(BadDispatcherStorage)
    contract2_bad_verify_state_lib = creator.deploy(ContractV2BadVerifyState)
    with brownie.reverts():
        creator.deploy(Dispatcher, contract0_bad_lib.address)
    with brownie.reverts():
        creator.deploy(Dispatcher, contract2_bad_verify_state_lib.address)

    # Deploy contracts and dispatcher for them
    contract1_lib = creator.deploy(ContractV1, 1)
    contract2_lib = creator.deploy(ContractV2, 1)
    contract3_lib = creator.deploy(ContractV3, 2)
    contract4_lib = creator.deploy(ContractV4, 3)
    contract2_bad_storage_lib = creator.deploy(ContractV2BadStorage)
    dispatcher = creator.deploy(Dispatcher, contract1_lib.address)
    assert contract1_lib.address == dispatcher.target()
    assert dispatcher.implementation() == contract1_lib.address
    assert dispatcher.proxyType() == 2

    tx = history[-1]
    assert "Upgraded" in tx.events
    event = tx.events["Upgraded"]
    assert NULL_ADDRESS == event["from"]
    assert contract1_lib.address == event["to"]
    assert creator == event["owner"]

    assert "StateVerified" in tx.events
    event = tx.events["StateVerified"]
    assert contract1_lib.address == event["testTarget"]
    assert creator == event["sender"]

    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract1_lib.address == event["target"]
    assert creator == event["sender"]

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = Contract.from_abi(
        name="ContractV1", abi=contract1_lib.abi, address=dispatcher.address
    )

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with brownie.reverts():
        dispatcher.verifyState(contract1_lib.address, {"from": creator})
    with brownie.reverts():
        contract1_lib.finishUpgrade(contract1_lib.address, {"from": creator})
    with brownie.reverts():
        contract1_lib.verifyState(contract1_lib.address, {"from": creator})

    # Check values and methods before upgrade
    assert 1 == contract_instance.storageValue()
    assert 10 == contract_instance.returnValue()
    contract_instance.setStorageValue(5, {"from": creator})
    assert 5 == contract_instance.storageValue()
    contract_instance.pushArrayValue(12, {"from": creator})
    assert 1 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    contract_instance.pushArrayValue(232, {"from": creator})
    assert 2 == contract_instance.getArrayValueLength()
    assert 232 == contract_instance.arrayValues(1)
    contract_instance.setMappingValue(14, 41, {"from": creator})
    assert 41 == contract_instance.mappingValues(14)
    contract_instance.pushStructureValue1(3, {"from": creator})
    assert 3 == contract_instance.arrayStructures(0)
    contract_instance.pushStructureArrayValue1(0, 11, {"from": creator})
    contract_instance.pushStructureArrayValue1(0, 111, {"from": creator})
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    contract_instance.pushStructureValue2(4, {"from": creator})
    assert 4 == contract_instance.mappingStructures(0)
    contract_instance.pushStructureArrayValue2(0, 12, {"from": creator})
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    contract_instance.setDynamicallySizedValue("Hola", {"from": creator})
    assert "Hola" == contract_instance.dynamicallySizedValue()

    # Only owner can change target address for the dispatcher
    with brownie.reverts():
        dispatcher.upgrade(contract2_lib.address, {"from": account})

    # Can't upgrade to the bad version
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, {"from": creator})

    # Upgrade contract
    assert contract1_lib.address == dispatcher.target()
    tx = dispatcher.upgrade(contract2_lib.address, {"from": creator})
    assert contract2_lib.address == dispatcher.target()

    brownie.network.event._add_deployment_topics(address=dispatcher.address, abi=dispatcher.abi)
    assert "Upgraded" in tx.events
    event = tx.events["Upgraded"]
    assert contract1_lib.address == event["from"]
    assert contract2_lib.address == event["to"]
    assert creator == event["owner"]

    assert "StateVerified" in tx.events
    events = tx.events["StateVerified"]
    assert len(events) == 2
    event = events[0]
    assert contract2_lib.address == event["testTarget"]
    assert creator == event["sender"]
    assert event == events[1]

    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract2_lib.address == event["target"]
    assert creator == event["sender"]

    # Check values and methods after upgrade
    assert 20 == contract_instance.returnValue()
    assert 5 == contract_instance.storageValue()
    contract_instance.setStorageValue(5, {"from": creator})
    assert 10 == contract_instance.storageValue()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    contract_instance.setMappingValue(13, 31, {"from": creator})
    assert 41 == contract_instance.mappingValues(14)
    assert 31 == contract_instance.mappingValues(13)
    contract_instance.pushStructureValue1(4, {"from": creator})
    assert 3 == contract_instance.arrayStructures(0)
    assert 4 == contract_instance.arrayStructures(1)
    contract_instance.pushStructureArrayValue1(0, 12, {"from": creator})
    assert 11 == contract_instance.getStructureArrayValue1(0, 0)
    assert 111 == contract_instance.getStructureArrayValue1(0, 1)
    assert 12 == contract_instance.getStructureArrayValue1(0, 2)
    contract_instance.pushStructureValue2(5, {"from": creator})
    assert 4 == contract_instance.mappingStructures(0)
    assert 5 == contract_instance.mappingStructures(1)
    contract_instance.pushStructureArrayValue2(0, 13, {"from": creator})
    assert 12 == contract_instance.getStructureArrayValue2(0, 0)
    assert 13 == contract_instance.getStructureArrayValue2(0, 1)
    assert "Hola" == contract_instance.dynamicallySizedValue()
    contract_instance.setDynamicallySizedValue("Hello", {"from": creator})
    assert "Hello" == contract_instance.dynamicallySizedValue()

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = Contract.from_abi(
        name="ContractV2", abi=contract2_lib.abi, address=dispatcher.address
    )

    # Check new method and finishUpgrade method
    assert 1 == contract_instance.storageValueToCheck()
    contract_instance.setStructureValueToCheck2(0, 55, {"from": creator})
    assert [4, 55] == contract_instance.mappingStructures(0)

    # Can't downgrade to the first version due to new storage variables
    with brownie.reverts():
        dispatcher.upgrade(contract1_lib.address, {"from": creator})

    # And can't upgrade to the bad version
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, {"from": creator})
    assert contract2_lib.address == dispatcher.target()

    # Only owner can rollback
    with brownie.reverts():
        dispatcher.rollback({"from": account})

    # Can rollback to the first version
    tx = dispatcher.rollback({"from": creator})
    assert contract1_lib.address == dispatcher.target()
    assert 2 == contract_instance.getArrayValueLength()
    assert 12 == contract_instance.arrayValues(0)
    assert 232 == contract_instance.arrayValues(1)
    assert 1 == contract_instance.storageValue()
    contract_instance.setStorageValue(5, {"from": creator})
    assert 5 == contract_instance.storageValue()

    brownie.network.event._add_deployment_topics(address=dispatcher.address, abi=dispatcher.abi)
    assert "RolledBack" in tx.events
    event = tx.events["RolledBack"]
    assert contract2_lib.address == event["from"]
    assert contract1_lib.address == event["to"]
    assert creator == event["owner"]

    assert "StateVerified" in tx.events
    event = tx.events["StateVerified"]
    assert contract2_lib.address == event["testTarget"]
    assert creator == event["sender"]

    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract1_lib.address == event["target"]
    assert creator == event["sender"]

    # Can't upgrade to the bad version
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_storage_lib.address, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract2_bad_verify_state_lib.address, {"from": creator})
    assert contract1_lib.address == dispatcher.target()

    # Create Event
    contract_instance = Contract.from_abi(
        name="ContractV1", abi=contract1_lib.abi, address=dispatcher.address
    )
    tx = contract_instance.createEvent(33, {"from": creator})
    assert "EventV1" in tx.events
    event = tx.events["EventV1"]
    assert 33 == event["value"]

    # Upgrade to the version 3
    tx1 = dispatcher.upgrade(contract2_lib.address, {"from": creator})
    tx2 = dispatcher.upgrade(contract3_lib.address, {"from": creator})

    brownie.network.event._add_deployment_topics(address=dispatcher.address, abi=dispatcher.abi)
    assert "Upgraded" in tx1.events
    event = tx1.events["Upgraded"]
    assert contract1_lib.address == event["from"]
    assert contract2_lib.address == event["to"]
    assert creator == event["owner"]

    assert "Upgraded" in tx2.events
    event = tx2.events["Upgraded"]
    assert contract2_lib.address == event["from"]
    assert contract3_lib.address == event["to"]
    assert creator == event["owner"]

    assert "StateVerified" in tx1.events
    events = tx1.events["StateVerified"]
    assert len(events) == 2
    event = events[0]
    assert contract2_lib.address == event["testTarget"]
    assert creator == event["sender"]
    assert event == events[1]

    assert "StateVerified" in tx2.events
    events = tx2.events["StateVerified"]
    assert len(events) == 2
    event = events[0]
    assert contract3_lib.address == event["testTarget"]
    assert creator == event["sender"]
    assert event == events[1]

    assert "UpgradeFinished" in tx1.events
    event = tx1.events["UpgradeFinished"]
    assert contract2_lib.address == event["target"]
    assert creator == event["sender"]

    assert "UpgradeFinished" in tx2.events
    event = tx2.events["UpgradeFinished"]
    assert contract3_lib.address == event["target"]
    assert creator == event["sender"]

    contract_instance = Contract.from_abi(
        name="ContractV3", abi=contract3_lib.abi, address=dispatcher.address
    )
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
    contract_instance.setAnotherStorageValue(77, {"from": creator})
    assert 77 == contract_instance.anotherStorageValue()

    # Create and check events
    tx = contract_instance.createEvent(22, {"from": creator})
    assert "EventV2" in tx.events
    event = tx.events["EventV2"]
    assert 22 == event["value"]

    # Check upgrading to the contract with explicit storage slots
    tx = dispatcher.upgrade(contract4_lib.address, {"from": creator})
    contract_instance = Contract.from_abi(
        name="ContractV4", abi=contract4_lib.abi, address=dispatcher.address
    )
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

    assert "StateVerified" in tx.events
    events = tx.events["StateVerified"]
    assert len(events) == 2
    event = events[0]
    assert contract4_lib.address == event["testTarget"]
    assert creator == event["sender"]
    assert event == events[1]

    assert "UpgradeFinished" in tx.events
    event = tx.events["UpgradeFinished"]
    assert contract4_lib.address == event["target"]
    assert creator == event["sender"]

    # Upgrade to the previous version - check that new `verifyState` can handle old contract
    tx = dispatcher.upgrade(contract3_lib.address, {"from": creator})
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

    assert "StateVerified" in tx.events
    events = tx.events["StateVerified"]
    assert len(events) == 2
    event = events[0]
    assert contract3_lib.address == event["testTarget"]
    assert creator == event["sender"]
    assert event == events[1]


def test_selfdestruct(Dispatcher, Destroyable, accounts):
    creator = accounts[0]
    account = accounts[1]

    # Deploy contract and destroy it
    contract1_lib = creator.deploy(Destroyable, 22)
    assert 22 == contract1_lib.constructorValue()
    contract1_lib.destroy()
    with pytest.raises(ValueError):
        contract1_lib.constructorValue()

    # Can't create dispatcher using address without contract
    with brownie.reverts():
        creator.deploy(Dispatcher, NULL_ADDRESS)
    with brownie.reverts():
        creator.deploy(Dispatcher, account)
    with brownie.reverts():
        creator.deploy(Dispatcher, contract1_lib.address)

    # Deploy contract again with a dispatcher targeting it
    contract2_lib = creator.deploy(Destroyable, 23)
    dispatcher = creator.deploy(Dispatcher, contract2_lib.address)
    assert contract2_lib.address == dispatcher.target()

    contract_instance = Contract.from_abi(
        name="Destroyable", abi=contract1_lib.abi, address=dispatcher.address
    )
    contract_instance.setFunctionValue(34, {"from": accounts[0]})
    assert 23 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Can't upgrade to an address without contract
    with brownie.reverts():
        dispatcher.upgrade(NULL_ADDRESS, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(account, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract1_lib.address, {"from": creator})

    # Destroy library
    contract2_lib.destroy()
    # Dispatcher must determine that there is no contract
    with brownie.reverts():
        contract_instance.constructorValue()

    # Can't upgrade to an address without contract
    with brownie.reverts():
        dispatcher.upgrade(NULL_ADDRESS, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(account, {"from": creator})
    with brownie.reverts():
        dispatcher.upgrade(contract1_lib.address, {"from": creator})

    # Deploy the same contract again and upgrade to this contract
    contract3_lib = creator.deploy(Destroyable, 24)
    dispatcher.upgrade(contract3_lib.address, {"from": creator})
    assert 24 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Can't rollback because the previous version is destroyed
    with brownie.reverts():
        dispatcher.rollback({"from": account})

    # Destroy again
    contract3_lib.destroy()
    with brownie.reverts():
        contract_instance.constructorValue()

    # Still can't rollback because the previous version is destroyed
    with brownie.reverts():
        dispatcher.rollback({"from": account})

    # Deploy the same contract twice and upgrade to the latest contract
    contract4_lib = creator.deploy(Destroyable, 25)
    contract5_lib = creator.deploy(Destroyable, 26)
    dispatcher.upgrade(contract4_lib.address, {"from": creator})
    dispatcher.upgrade(contract5_lib.address, {"from": creator})
    assert 26 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Destroy the previous version of the contract and try to rollback again
    contract4_lib.destroy()
    with brownie.reverts():
        dispatcher.rollback({"from": account})

    # Deploy the same contract again and upgrade
    contract6_lib = creator.deploy(Destroyable, 27)
    dispatcher.upgrade(contract6_lib.address, {"from": creator})
    assert 27 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()

    # Destroy the current version of the contract
    contract6_lib.destroy()
    # Now rollback must work, the previous version is fine
    dispatcher.rollback({"from": creator})
    assert 26 == contract_instance.constructorValue()
    assert 34 == contract_instance.functionValue()


def test_receive_fallback(Dispatcher, NoFallback, OnlyReceive, ReceiveFallback, accounts):
    creator = accounts[0]
    # Deploy first contract
    no_fallback_lib = NoFallback.deploy({"from": creator})
    dispatcher = Dispatcher.deploy(no_fallback_lib.address, {"from": creator})
    contract_instance = Contract.from_abi(
        name="NoFallback", abi=no_fallback_lib.abi, address=dispatcher.address
    )

    # Can't transfer ETH to this version of contract
    value = 10000
    with brownie.reverts():
        creator.transfer(contract_instance.address, value)
    assert contract_instance.balance() == 0

    # Upgrade to other contract
    receive_lib = OnlyReceive.deploy({"from": creator})
    dispatcher.upgrade(receive_lib.address)
    contract_instance = Contract.from_abi(
        name="OnlyReceive", abi=receive_lib.abi, address=dispatcher.address
    )

    # Transfer ETH and check which function was executed
    creator.transfer(contract_instance.address, value)
    assert contract_instance.value() == value
    assert contract_instance.receiveRequests() == 1
    assert contract_instance.balance() == value

    # Upgrade to other contract and transfer ETH again
    receive_fallback_lib = ReceiveFallback.deploy({"from": creator})
    dispatcher.upgrade(receive_fallback_lib.address)
    contract_instance = Contract.from_abi(
        name="ReceiveFallback", abi=receive_fallback_lib.abi, address=dispatcher.address
    )

    creator.transfer(contract_instance.address, value)
    assert contract_instance.receiveRequests() == 2
    assert contract_instance.value() == 2 * value
    assert contract_instance.fallbackRequests() == 0
    assert contract_instance.balance() == 2 * value
