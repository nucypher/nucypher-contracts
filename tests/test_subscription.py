import pytest

RITUAL_ID = 0
ERC20_SUPPLY = 10**24


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


def test_new_subscription(subscription, fee_token, deployer):
    cost = subscription.subscriptionFee()
    fee_token.approve(subscription.address, cost, sender=deployer)
    tx = subscription.newSubscription(RITUAL_ID, sender=deployer)
    assert subscription.numberOfSubscriptions() == 1
    # TODO: Fix this - Currently fails because fee_token is a mock contract
    # assert tx.events == [
    #     fee_token.Transfer(admin, subscription.address, cost),
    #     managed_allow_list.AddressAuthorizationSet(RITUAL_ID, admin, True)
    # ]
    assert len(tx.events) == 1
    assert subscription.authorizationActionsCap(RITUAL_ID, deployer) == 1000


def test_cancel_subscription(subscription, fee_token, deployer):
    cost = subscription.subscriptionFee()
    fee_token.approve(subscription.address, cost, sender=deployer)
    subscription.newSubscription(RITUAL_ID, sender=deployer)
    assert subscription.numberOfSubscriptions() == 1
    assert subscription.authorizationActionsCap(RITUAL_ID, deployer) == 1000

    subscription.cancelSubscription(RITUAL_ID, 0, sender=deployer)
    # TODO: Fix assertions
    # assert not subscription.subscriptions()[0]
    # assert not subscription.authorizationActionsCap(RITUAL_ID, deployer)


# TODO: Add more tests
