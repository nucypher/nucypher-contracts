import pytest

import brownie

from brownie import chain

@pytest.fixture(scope="session")
def subscription_manager(SubscriptionManager, accounts):
    return accounts[0].deploy(SubscriptionManager)

def test_create_policy(subscription_manager, accounts):
    policy_id = b'feed your head!!'
    alice = accounts[1]
    duration = 1000
    fee = subscription_manager.RATE_PER_SECOND() * duration
    start = chain.time()
    end = start + duration
    subscription_manager.createPolicy(policy_id, alice, start, end,
        {'from': alice, 'value': fee })
    assert subscription_manager.balance() == fee

    assert subscription_manager.isPolicyActive(policy_id)

    policy = subscription_manager.policies(policy_id)
    assert policy[0] == alice
    assert policy[1] == "0x0000000000000000000000000000000000000000"
    assert policy[2] == start
    assert policy[3] == end
    
def test_create_policy_with_same_id(subscription_manager, accounts):
    policy_id = b'feed your head!!'
    alice = accounts[1]
    duration = 1000
    fee = subscription_manager.RATE_PER_SECOND() * duration
    with brownie.reverts("Policy is currently active"):
        subscription_manager.createPolicy(policy_id, alice, chain.time(), chain.time() + duration,
                                          {'from': alice, 'value': fee })

def test_sweep(subscription_manager, accounts):
    recipient = accounts[2]
    initial_balance = recipient.balance()
    expected_balance = initial_balance + subscription_manager.RATE_PER_SECOND() * 1000
    subscription_manager.sweep(recipient, {'from': accounts[0] })
    assert recipient.balance() == expected_balance
