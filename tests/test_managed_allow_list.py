import os

import ape
import pytest
from eth_account.messages import encode_defunct
from web3 import Web3


@pytest.fixture(scope="module")
def initiator(accounts):
    initiator_index = 1
    assert len(accounts) >= initiator_index
    return accounts[initiator_index]


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer_index = 2
    assert len(accounts) >= deployer_index
    return accounts[deployer_index]


@pytest.fixture()
def fee_model(project, deployer):
    contract = project.FeeModelForManagedAllowListMock.deploy(sender=deployer)
    return contract


@pytest.fixture()
def coordinator(project, deployer, fee_model):
    contract = project.CoordinatorForManagedAllowListMock.deploy(
        fee_model.address,
        sender=deployer,
    )
    return contract


@pytest.fixture()
def managed_allow_list(project, deployer, coordinator, oz_dependency):
    contract = project.ManagedAllowList.deploy(coordinator.address, sender=deployer)
    encoded_initializer_function = b""
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.ManagedAllowList.at(proxy.address)
    return proxy_contract


def test_authorize_using_global_allow_list(coordinator, deployer, initiator, managed_allow_list):
    # This block mocks the signature of a threshold decryption request
    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=deployer.private_key)
    signature = signed_digest.signature

    ritual_id = 0
    cohort_admin_role = managed_allow_list.ritualRole(
        ritual_id, managed_allow_list.COHORT_ADMIN_BASE()
    )
    auth_admin_role = managed_allow_list.ritualRole(ritual_id, managed_allow_list.AUTH_ADMIN_BASE())

    # Not authorized
    assert not managed_allow_list.isAuthorized(0, bytes(signature), bytes(digest))

    # Negative test cases for authorization
    with ape.reverts("Only auth admin is permitted"):
        managed_allow_list.authorize(ritual_id, [deployer.address], sender=deployer)

    with ape.reverts("Only ritual authority is permitted"):
        managed_allow_list.initializeCohortAdminRole(ritual_id, sender=deployer)

    coordinator.initiateRitual(ritual_id, initiator, sender=initiator)

    with ape.reverts("Only ritual authority is permitted"):
        managed_allow_list.initializeCohortAdminRole(ritual_id, sender=deployer)

    managed_allow_list.initializeCohortAdminRole(ritual_id, sender=initiator)
    assert managed_allow_list.hasRole(cohort_admin_role, initiator)

    managed_allow_list.grantRole(auth_admin_role, deployer, sender=initiator)
    managed_allow_list.authorize(ritual_id, [deployer.address], sender=deployer)

    managed_allow_list.grantRole(auth_admin_role, initiator, sender=initiator)
    with ape.reverts("Encryptor must be authorized by the sender first"):
        managed_allow_list.deauthorize(ritual_id, [deployer.address], sender=initiator)
