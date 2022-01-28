import pytest

import brownie

from brownie import chain

@pytest.fixture(scope="session")
def subscription_manager(SubscriptionManager, accounts):
    sm = accounts[0].deploy(SubscriptionManager)
    sm.initialize(42)
    return sm

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
