import ape
import pytest
from web3 import Web3

INITIAL_FEE_RATE = Web3.to_wei(1, "gwei")


@pytest.fixture(scope="module")
def proxy_admin(accounts, oz_dependency):
    deployer = accounts[0]
    return deployer.deploy(oz_dependency.ProxyAdmin, deployer)


@pytest.fixture(scope="module")
def subscription_manager_logic(project, accounts):
    return project.SubscriptionManager.deploy(sender=accounts[0])


@pytest.fixture(scope="module")
def transparent_proxy(proxy_admin, subscription_manager_logic, accounts, oz_dependency):
    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    return accounts[0].deploy(
        oz_dependency.TransparentUpgradeableProxy,
        subscription_manager_logic.address,
        proxy_admin.address,
        calldata,
    )


@pytest.fixture(scope="module")
def subscription_manager(transparent_proxy, project):
    sm = project.SubscriptionManager.at(transparent_proxy.address)
    return sm


def test_initial_parameters(subscription_manager, subscription_manager_logic):
    assert subscription_manager.feeRate() == INITIAL_FEE_RATE
    assert subscription_manager_logic.feeRate() == 0


def test_create_policy(subscription_manager, accounts, chain):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    start = chain.pending_timestamp
    end = start + duration

    expectedFee = subscription_manager.feeRate() * duration * size
    fee = subscription_manager.getPolicyCost(size, start, end)
    assert fee == expectedFee

    tx = subscription_manager.createPolicy(
        policy_id, alice, size, start, end, sender=alice, value=fee
    )

    policy = subscription_manager.getPolicy(policy_id)

    assert subscription_manager.isPolicyActive(policy_id)
    assert policy[0] == alice
    assert policy[1] == start
    assert policy[2] == end
    assert policy[3] == size
    assert policy[4] == "0x0000000000000000000000000000000000000000"

    assert tx.events == [
        subscription_manager.PolicyCreated(
            policyId=policy_id,
            sponsor=alice,
            owner=alice,
            size=size,
            startTimestamp=start,
            endTimestamp=end,
            cost=fee,
        )
    ]


def test_create_policy_with_sponsor(subscription_manager, accounts, chain):
    policy_id = b"from the sponsor"
    alice = accounts[1]
    sponsor = accounts[2]
    duration = 1000
    size = 3
    start = chain.pending_timestamp
    end = start + duration

    fee = subscription_manager.getPolicyCost(size, start, end)

    tx = subscription_manager.createPolicy(
        policy_id, alice, size, start, end, sender=sponsor, value=fee
    )

    policy = subscription_manager.getPolicy(policy_id)

    assert subscription_manager.isPolicyActive(policy_id)
    assert policy[0] == sponsor
    assert policy[1] == start
    assert policy[2] == end
    assert policy[3] == size
    assert policy[4] == alice

    assert tx.events == [
        subscription_manager.PolicyCreated(
            policyId=policy_id,
            sponsor=sponsor,
            owner=alice,
            size=size,
            startTimestamp=start,
            endTimestamp=end,
            cost=fee,
        )
    ]


def test_create_policy_with_same_id(subscription_manager, accounts, chain):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    start = chain.pending_timestamp
    end = start + duration
    fee = subscription_manager.getPolicyCost(size, start, end)

    subscription_manager.createPolicy(
        policy_id,
        alice,
        size,
        start,
        end,
        sender=alice,
        value=fee,
    )
    with ape.reverts("Policy is currently active"):
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            start,
            end,
            sender=alice,
            value=fee,
        )


def test_create_policy_again_after_duration_time(subscription_manager, accounts, chain):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000 + 1
    size = 3
    start = chain.pending_timestamp
    end = start + duration
    fee = subscription_manager.getPolicyCost(size, start, end)
    chain.pending_timestamp += duration

    subscription_manager.createPolicy(
        policy_id,
        alice,
        size,
        chain.pending_timestamp,
        chain.pending_timestamp + duration,
        sender=alice,
        value=fee,
    )

    assert subscription_manager.isPolicyActive(policy_id)


def test_create_policy_transfers_eth(subscription_manager, accounts, chain):
    policy_id = b"transfers_eth!!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    start = chain.pending_timestamp
    end = start + duration
    fee = subscription_manager.getPolicyCost(size, start, end)

    alice_expected_balance = alice.balance - fee
    contract_expected_balance = subscription_manager.balance + fee

    tx = subscription_manager.createPolicy(
        policy_id,
        alice,
        size,
        start,
        end,
        sender=alice,
        value=fee,
    )

    assert alice.balance == alice_expected_balance - tx.total_fees_paid
    assert subscription_manager.balance == contract_expected_balance


def test_create_policy_with_invalid_timestamp(subscription_manager, accounts, chain):
    policy_id = b"invalidTimestamp"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = 0
    start = chain.pending_timestamp
    invalid_end = chain.pending_timestamp - duration
    with ape.reverts("Invalid timestamps"):
        subscription_manager.createPolicy(
            policy_id, alice, size, start, invalid_end, sender=alice, value=fee
        )


def test_create_policy_with_invalid_fee(subscription_manager, accounts, chain):
    policy_id = b"invalidTimestamp"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = (subscription_manager.feeRate() * duration * size) - 1
    with ape.reverts():
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            chain.pending_timestamp,
            chain.pending_timestamp + duration,
            sender=alice,
            value=fee,
        )


def test_create_policy_with_invalid_node_size(subscription_manager, accounts, chain):
    policy_id = b"invalid nodesize"
    alice = accounts[1]
    duration = 1000
    size = 0
    fee = subscription_manager.feeRate() * duration * size
    with ape.reverts():
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            chain.pending_timestamp,
            chain.pending_timestamp + duration,
            sender=alice,
            value=fee,
        )


def test_set_fee_rate(subscription_manager, accounts):
    new_rate = Web3.to_wei(2, "gwei")
    subscription_manager.setFeeRate(new_rate, sender=accounts[0])
    assert new_rate == subscription_manager.feeRate()


def test_set_fee_rate_with_no_set_rate_role(subscription_manager, accounts):
    new_rate = Web3.to_wei(10, "gwei")
    with ape.reverts():
        subscription_manager.setFeeRate(new_rate, sender=accounts[1])


def test_sweep_with_no_withdraw_role(subscription_manager, accounts):
    recipient = accounts[2]
    with ape.reverts():
        subscription_manager.sweep(recipient, sender=accounts[1])


def test_sweep(subscription_manager, accounts):
    recipient = accounts[2]
    initial_balance = recipient.balance
    expected_balance = initial_balance + subscription_manager.balance
    subscription_manager.sweep(recipient, sender=accounts[0])
    assert recipient.balance == expected_balance
