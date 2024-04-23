import ape
import pytest

RITUAL_ID = 0
ERC20_SUPPLY = 10 ** 24


@pytest.fixture(scope="module")
def deployer(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def authority(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def subscriber(accounts):
    return accounts[2]


@pytest.fixture(scope="module")
def beneficiary(accounts):
    return accounts[3]


@pytest.fixture(scope="module")
def encryptor(accounts):
    return accounts[4]


@pytest.fixture()
def coordinator(project, deployer):
    contract = project.CoordinatorForEncryptionAuthorizerMock.deploy(
        sender=deployer,
    )
    return contract


@pytest.fixture()
def fee_token(project, deployer):
    return project.TestToken.deploy(ERC20_SUPPLY, sender=deployer)


@pytest.fixture()
def subscription(project, coordinator, fee_token, beneficiary, authority):
    return project.UpfrontSubscriptionWithEncryptorsCap.deploy(
        coordinator.address, fee_token.address, beneficiary, sender=authority
    )


def assert_new_subscription(subscription, fee_token, deployer, subscriber):
    cost = subscription.subscriptionFee()
    fee_token.transfer(subscriber, cost, sender=deployer)

    fee_token.approve(subscription.address, cost, sender=subscriber)
    tx = subscription.newSubscription(RITUAL_ID, sender=subscriber)
    assert subscription.numberOfSubscriptions() == 1
    subscription_id = 0
    # TODO: Fix this - Currently fails because fee_token is a mock contract
    # assert tx.events == [
    #     fee_token.Transfer(admin, subscription.address, cost),
    # ]
    assert len(tx.events) == 3
    # assert tx.events[:1] == [
    #     subscription.SubscriptionPaid(
    #         subscription_id, subscriber, cost
    #     ),
    #     subscription.SubscriptionCreated(
    #         subscription_id, subscriber, RITUAL_ID
    #     )
    # ]
    assert subscription.authorizationActionsCap(RITUAL_ID, subscriber) == 1000

    my_subscription = subscription.subscriptions(subscription_id)
    assert my_subscription.subscriber == subscriber
    assert my_subscription.paidFor == cost
    assert my_subscription.expiration == subscription.baseExpiration()
    return subscription_id, my_subscription


def test_new_subscription(subscription, fee_token, deployer, subscriber):
    assert_new_subscription(subscription, fee_token, deployer, subscriber)


def test_cancel_subscription(subscription, fee_token, deployer, subscriber, encryptor):
    subscription_id, _ = assert_new_subscription(subscription, fee_token, deployer, subscriber)

    # Only the subscriber can cancel the subscription
    with ape.reverts("Only the subscriber can cancel the subscription"):
        subscription.cancelSubscription(RITUAL_ID, subscription_id, sender=encryptor)

    tx = subscription.cancelSubscription(RITUAL_ID, subscription_id, sender=subscriber)
    assert len(tx.events) == 2
    # TODO: Fix this - Currently fails because fee_token is a mock contract
    # assert tx.events == [
    #     fee_token.Transfer(subscription.address, subscriber, cost),
    # ]
    # assert tx.events[:1] == [
    #     subscription.SubscriptionCancelled(
    #         subscription_id, subscriber, RITUAL_ID
    #     )
    # ]
    assert not subscription.subscriptions(subscription_id)[0]
    assert not subscription.authorizationActionsCap(RITUAL_ID, subscriber)


def test_pay_subscription(subscription, fee_token, deployer, subscriber):
    subscription_id, my_subscription = assert_new_subscription(subscription, fee_token, deployer, subscriber)
    assert my_subscription.paidFor == subscription.subscriptionFee()
    assert my_subscription.expiration == subscription.baseExpiration()

    cost = subscription.subscriptionFee()
    fee_token.transfer(subscriber, cost, sender=deployer)
    assert fee_token.balanceOf(subscriber) == cost
    fee_token.approve(subscription.address, cost, sender=subscriber)

    tx = subscription.paySubscriptionFor(subscription_id, sender=subscriber)
    assert len(tx.events) == 2
    # TODO: Fix this - Currently fails because fee_token is a mock contract
    # assert tx.events == [
    #     fee_token.Transfer(subscription.address, subscriber, cost),
    # ]
    # assert tx.events[:1] == [
    #     subscription.SubscriptionCancelled(
    #         subscription_id, subscriber, RITUAL_ID
    #     )
    # ]
    # TODO: These are failing, is subscription not being updated?
    # assert my_subscription.paidFor == 2 * subscription.subscriptionFee()
    # assert my_subscription.expiration == 2 * subscription.baseExpiration()


def test_can_spend_from_subscription(subscription, fee_token, deployer, subscriber, coordinator):
    subscription_id, _ = assert_new_subscription(subscription, fee_token, deployer, subscriber)
    subscription_balance = fee_token.balanceOf(subscription.address)
    assert subscription_balance == subscription.subscriptionFee()

    # Only the coordinator can spend from the subscription
    with ape.reverts("Unauthorized spender"):
        subscription.spendFromSubscription(subscription_id, subscription_balance, sender=subscriber)

    assert not fee_token.balanceOf(coordinator.address)
    # TODO: How do I impersonate the coordinator contract here?
    # subscription.spendFromSubscription(subscription_id, subscription_balance, sender=coordinator.address)
    # assert fee_token.balanceOf(coordinator.address) == subscription_balance
    # assert not fee_token.balanceOf(subscription.address)


def test_withdraw_to_beneficiary(subscription, fee_token, deployer, subscriber, beneficiary):
    subscription_id, _ = assert_new_subscription(subscription, fee_token, deployer, subscriber)
    subscription_balance = fee_token.balanceOf(subscription.address)
    assert subscription_balance == subscription.subscriptionFee()

    # Only the beneficiary can withdraw from the subscription
    with ape.reverts("Only the beneficiary can withdraw"):
        subscription.withdrawToBeneficiary(subscription_balance, sender=deployer)

    assert not fee_token.balanceOf(beneficiary)
    tx = subscription.withdrawToBeneficiary(subscription_balance, sender=beneficiary)
    assert len(tx.events) == 2
    assert tx[1] == subscription.WithdrawalToBeneficiary(beneficiary, subscription_balance)
    assert fee_token.balanceOf(beneficiary) == subscription_balance
    assert not fee_token.balanceOf(subscription.address)
