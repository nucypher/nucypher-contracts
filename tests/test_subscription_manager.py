import pytest

from brownie import chain

@pytest.fixture(scope="session")
def subscription_manager(SubscriptionManager, accounts):
    return accounts[0].deploy(SubscriptionManager)

def test_create_policy(subscription_manager, accounts):
    policy_id = b'feed your head!!'
    alice = accounts[1]
    duration = 1000
    fee = subscription_manager.RATE_PER_SECOND() * duration
    subscription_manager.createPolicy(policy_id, alice, chain.time(), chain.time() + duration,
        {'from': alice, 'value': fee })
    assert subscription_manager.balance() == fee

def test_sweep(subscription_manager, accounts):
    recipient = accounts[2]
    initial_balance = recipient.balance()
    expected_balance = initial_balance + subscription_manager.RATE_PER_SECOND() * 1000
    subscription_manager.sweep(recipient, {'from': accounts[0] })
    assert recipient.balance() == expected_balance
