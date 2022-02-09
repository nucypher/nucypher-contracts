import brownie
import pytest
from brownie import Contract, chain
from brownie.convert.datatypes import Wei
from brownie.project.main import Project

INITIAL_FEE_RATE = Wei("1 gwei")


@pytest.fixture(scope="session")
def oz():
    brownie_packages = brownie._config._get_data_folder().joinpath("packages")
    oz_dependency_path = "OpenZeppelin/openzeppelin-contracts@4.4.2/"
    project = Project("OZ", brownie_packages.joinpath(oz_dependency_path))
    return project


@pytest.fixture(scope="session")
def proxy_admin(oz, accounts):
    return accounts[0].deploy(oz.ProxyAdmin)


@pytest.fixture(scope="session")
def subscription_manager_logic(SubscriptionManager, accounts):
    return accounts[0].deploy(SubscriptionManager)


@pytest.fixture(scope="session")
def transparent_proxy(oz, proxy_admin, subscription_manager_logic, accounts):

    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    return oz.TransparentUpgradeableProxy.deploy(
        subscription_manager_logic.address, proxy_admin.address, calldata, {"from": accounts[0]}
    )


@pytest.fixture(scope="session")
def subscription_manager(transparent_proxy, subscription_manager_logic):
    sm = Contract.from_abi(
        "SubscriptionManager", transparent_proxy.address, subscription_manager_logic.abi, owner=None
    )
    return sm


def test_initial_parameters(subscription_manager, subscription_manager_logic):
    assert subscription_manager.feeRate() == INITIAL_FEE_RATE
    assert subscription_manager_logic.feeRate() == 0


def test_create_policy(subscription_manager, accounts):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size
    start = chain.time()
    end = start + duration
    subscription_manager.createPolicy(
        policy_id, alice, size, start, end, {"from": alice, "value": fee}
    )

    policy = subscription_manager.getPolicy(policy_id)

    assert subscription_manager.isPolicyActive(policy_id)
    assert policy[0] == alice
    assert policy[1] == start
    assert policy[2] == end
    assert policy[3] == size
    assert policy[4] == "0x0000000000000000000000000000000000000000"


def test_create_policy_with_same_id(subscription_manager, accounts):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size

    with brownie.reverts("Policy is currently active"):
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            chain.time(),
            chain.time() + duration,
            {"from": alice, "value": fee},
        )


def test_create_policy_again_after_duration_time(subscription_manager, accounts):
    policy_id = b"feed your head!!"
    alice = accounts[1]
    duration = 1000 + 1
    size = 3
    fee = subscription_manager.feeRate() * duration * size

    chain.sleep(duration)

    subscription_manager.createPolicy(
        policy_id, alice, size, chain.time(), chain.time() + duration, {"from": alice, "value": fee}
    )

    assert subscription_manager.isPolicyActive(policy_id)


def test_create_policy_transfers_eth(subscription_manager, accounts):
    policy_id = b"transfers_eth!!!"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size
    start = chain.time()
    end = start + duration

    alice_expected_balance = alice.balance() - fee
    contract_expected_balance = subscription_manager.balance() + fee

    subscription_manager.createPolicy(
        policy_id, alice, size, start, end, {"from": alice, "value": fee}
    )

    assert alice.balance() == alice_expected_balance
    assert subscription_manager.balance() == contract_expected_balance


def test_create_policy_with_invalid_timestamp(subscription_manager, accounts):
    policy_id = b"invalidTimestamp"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = subscription_manager.feeRate() * duration * size
    start = chain.time()
    invalid_end = chain.time() - duration
    with brownie.reverts("Invalid timestamps"):
        subscription_manager.createPolicy(
            policy_id, alice, size, start, invalid_end, {"from": alice, "value": fee}
        )


def test_create_policy_with_invalid_fee(subscription_manager, accounts):
    policy_id = b"invalidTimestamp"
    alice = accounts[1]
    duration = 1000
    size = 3
    fee = (subscription_manager.feeRate() * duration * size) - 1
    with brownie.reverts():
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            chain.time(),
            chain.time() + duration,
            {"from": alice, "value": fee},
        )


def test_create_policy_with_invalid_node_size(subscription_manager, accounts):
    policy_id = b"invalid nodesize"
    alice = accounts[1]
    duration = 1000
    size = 0
    fee = subscription_manager.feeRate() * duration * size
    with brownie.reverts():
        subscription_manager.createPolicy(
            policy_id,
            alice,
            size,
            chain.time(),
            chain.time() + duration,
            {"from": alice, "value": fee},
        )


def test_set_fee_rate(subscription_manager, accounts):
    new_rate = Wei("2 gwei")
    subscription_manager.setFeeRate(new_rate, {"from": accounts[0]})
    assert new_rate == subscription_manager.feeRate()


def test_set_fee_rate_with_no_set_rate_role(subscription_manager, accounts):
    new_rate = Wei("10 gwei")
    with brownie.reverts():
        subscription_manager.setFeeRate(new_rate, {"from": accounts[1]})


def test_sweep_with_no_withdraw_role(subscription_manager, accounts):
    recipient = accounts[2]
    with brownie.reverts():
        subscription_manager.sweep(recipient, {"from": accounts[1]})


def test_sweep(subscription_manager, accounts):
    recipient = accounts[2]
    initial_balance = recipient.balance()
    expected_balance = initial_balance + subscription_manager.balance()
    subscription_manager.sweep(recipient, {"from": accounts[0]})
    assert recipient.balance() == expected_balance
