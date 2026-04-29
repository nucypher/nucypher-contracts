import os

import ape
import pytest
from ape.utils import ZERO_ADDRESS
from eth_account.messages import encode_defunct
from web3 import Web3


@pytest.fixture(scope="module")
def initiator(accounts):
    initiator_index = 1
    return accounts[initiator_index]


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer_index = 2
    return accounts[deployer_index]


@pytest.fixture()
def fee_model(project, deployer):
    contract = project.SharedSubscriptionForSharedAllowListMock.deploy(sender=deployer)
    return contract


@pytest.fixture()
def coordinator(project, deployer, fee_model):
    contract = project.CoordinatorForSharedAllowListMock.deploy(
        fee_model.address,
        sender=deployer,
    )
    return contract


@pytest.fixture()
def shared_allow_list(project, deployer, coordinator, oz_dependency):
    contract = project.SharedAllowList.deploy(coordinator.address, sender=deployer)
    encoded_initializer_function = b""
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.SharedAllowList.at(proxy.address)
    return proxy_contract


def test_authorize(coordinator, fee_model, deployer, initiator, shared_allow_list):
    # This block mocks the signature of a threshold decryption request
    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=deployer.private_key)
    signature = signed_digest.signature

    ritual_id = 0

    with ape.reverts("Not authorized"):
        shared_allow_list.authorize(ritual_id, [deployer.address], sender=initiator)

    fee_model.setAuthAdmin(initiator.address, True, sender=deployer)

    # Not authorized
    assert not shared_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    # Negative test cases for authorization
    tx = shared_allow_list.authorize(ritual_id, [deployer.address], sender=initiator)
    events = [event for event in tx.events if event.event_name == "AddressAuthorizationSet"]
    assert events == [
        shared_allow_list.AddressAuthorizationSet(
            ritualId=ritual_id, _address=deployer.address, isAuthorized=True
        )
    ]

    assert shared_allow_list.getAuthAdmin(ritual_id, deployer.address) == initiator.address
    assert shared_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    fee_model.setAuthAdmin(initiator.address, False, sender=initiator)
    with ape.reverts("Not authorized"):
        shared_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))
    with ape.reverts("Not authorized"):
        shared_allow_list.authorize(ritual_id, [deployer.address], sender=initiator)

    fee_model.setAuthAdmin(initiator.address, True, sender=initiator)
    fee_model.setAuthAdmin(deployer.address, True, sender=initiator)
    with ape.reverts("Address authorized by different admin"):
        shared_allow_list.deauthorize(ritual_id, [deployer.address], sender=deployer)
    with ape.reverts("Address authorized by different admin"):
        shared_allow_list.authorize(ritual_id, [deployer.address], sender=deployer)

    tx = shared_allow_list.deauthorize(ritual_id, [deployer.address], sender=initiator)

    assert not shared_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))
    events = [event for event in tx.events if event.event_name == "AddressAuthorizationSet"]
    assert events == [
        shared_allow_list.AddressAuthorizationSet(
            ritualId=ritual_id, _address=deployer.address, isAuthorized=False
        )
    ]
    assert shared_allow_list.getAuthAdmin(ritual_id, deployer.address) == ZERO_ADDRESS
