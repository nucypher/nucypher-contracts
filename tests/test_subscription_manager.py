import pytest

import brownie

from brownie import Contract, chain
from brownie.convert.datatypes import Wei
from brownie.project.main import Project

from pathlib import Path

INITIAL_FEE_RATE = Wei("1 gwei")

@pytest.fixture(scope="session")
def oz():
    brownie_packages = brownie._config._get_data_folder().joinpath('packages')
    oz_dependency_path = 'OpenZeppelin/openzeppelin-contracts@4.4.2/'
    project = Project("OZ", brownie_packages.joinpath(oz_dependency_path))
    return project

@pytest.fixture(scope="session")
def proxy_admin(oz, accounts):
    return accounts[0].deploy(oz.ProxyAdmin)

@pytest.fixture(scope="session")
def subscription_manager_logic(SubscriptionManager, accounts):
    return accounts[0].deploy(SubscriptionManager)

@pytest.fixture(scope="session")
def transparent_proxy(oz,
                      proxy_admin, subscription_manager_logic, accounts):

    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    return oz.TransparentUpgradeableProxy.deploy(
        subscription_manager_logic.address,
        proxy_admin.address,
        calldata,
        {'from': accounts[0]})

@pytest.fixture(scope="session")
def subscription_manager(transparent_proxy, subscription_manager_logic):
    sm = Contract.from_abi("SubscriptionManager", transparent_proxy.address, subscription_manager_logic.abi, owner=None)
    return sm

def test_initial_parameters(subscription_manager, subscription_manager_logic):
    assert subscription_manager.feeRate() == INITIAL_FEE_RATE
    assert subscription_manager_logic.feeRate() == 0

def test_create_policy(subscription_manager, accounts):
    policy_id = b'feed your head!!'
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size
    start = chain.time()
    end = start + duration
    subscription_manager.createPolicy(policy_id, alice, size, start, end,
        {'from': alice, 'value': fee })
    assert subscription_manager.balance() == fee

    assert subscription_manager.isPolicyActive(policy_id)

    policy = subscription_manager.getPolicy(policy_id)
    assert policy[0] == alice
    assert policy[1] == start
    assert policy[2] == end
    assert policy[3] == size
    assert policy[4] == "0x0000000000000000000000000000000000000000"
    
def test_create_policy_with_same_id(subscription_manager, accounts):
    policy_id = b'feed your head!!'
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size
    with brownie.reverts("Policy is currently active"):
        subscription_manager.createPolicy(policy_id, alice, size, chain.time(), chain.time() + duration,
                                          {'from': alice, 'value': fee })

def test_sweep(subscription_manager, accounts):
    recipient = accounts[2]
    initial_balance = recipient.balance()
    expected_balance = initial_balance + subscription_manager.feeRate() * 1000 * 3
    subscription_manager.sweep(recipient, {'from': accounts[0] })
    assert recipient.balance() == expected_balance
