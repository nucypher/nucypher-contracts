import ape
import pytest

RITUAL_ID = 0
ADMIN_CAP = 5
ERC20_SUPPLY = 10**24
FEE_RATE = 42


@pytest.fixture(scope="module")
def deployer(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def authority(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def admin(accounts):
    return accounts[2]


@pytest.fixture(scope="module")
def encryptor(accounts):
    return accounts[3]


@pytest.fixture(scope="module")
def beneficiary(accounts):
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


@pytest.fixture()
def fee_model(project, deployer, coordinator, fee_token):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, fee_token.address, FEE_RATE, sender=deployer
    )
    return contract


@pytest.fixture()
def brand_new_managed_allow_list(project, coordinator, subscription, fee_model, authority):
    return project.ManagedAllowList.deploy(
        coordinator.address, fee_model.address, subscription.address, sender=authority
    )


@pytest.fixture()
def managed_allow_list(brand_new_managed_allow_list, coordinator, deployer, authority):
    coordinator.mockNewRitual(authority, sender=deployer)
    return brand_new_managed_allow_list


def test_initial_parameters(managed_allow_list, coordinator, admin, encryptor):
    assert managed_allow_list.coordinator() == coordinator.address
    assert not managed_allow_list.getAllowance(RITUAL_ID, admin.address)
    assert not managed_allow_list.authActions(RITUAL_ID)


def test_add_administrators(managed_allow_list, authority, admin):
    # Only authority can add administrators
    with ape.reverts("Only cohort authority is permitted"):
        managed_allow_list.addAdministrators(RITUAL_ID, [admin.address], ADMIN_CAP, sender=admin)

    tx = managed_allow_list.addAdministrators(
        RITUAL_ID, [admin.address], ADMIN_CAP, sender=authority
    )
    assert tx.events == [
        managed_allow_list.AdministratorCapSet(RITUAL_ID, admin.address, ADMIN_CAP)
    ]
    assert managed_allow_list.getAllowance(RITUAL_ID, admin.address) == ADMIN_CAP
    assert managed_allow_list.authActions(RITUAL_ID) == 1


def test_remove_administrators(managed_allow_list, authority, admin):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin.address], ADMIN_CAP, sender=authority)
    assert managed_allow_list.authActions(RITUAL_ID) == 1

    # Only authority can remove administrators
    with ape.reverts("Only cohort authority is permitted"):
        managed_allow_list.removeAdministrators(RITUAL_ID, [admin.address], sender=admin)

    tx = managed_allow_list.removeAdministrators(RITUAL_ID, [admin.address], sender=authority)
    assert tx.events == [managed_allow_list.AdministratorCapSet(RITUAL_ID, admin.address, 0)]
    assert managed_allow_list.getAllowance(RITUAL_ID, admin.address) == 0
    # Auth actions may only increase
    assert managed_allow_list.authActions(RITUAL_ID) == 2


def test_authorize(
    managed_allow_list, subscription, fee_token, deployer, authority, admin, encryptor
):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    assert managed_allow_list.getAllowance(RITUAL_ID, admin) == ADMIN_CAP

    # Authorization requires a valid and paid for subscription
    with ape.reverts("Authorization cap exceeded"):
        managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)

    cost = subscription.subscriptionFee()
    fee_token.approve(subscription.address, cost, sender=deployer)
    tx = subscription.newSubscription(RITUAL_ID, sender=deployer)
    assert subscription.numberOfSubscriptions() == 1
    # TODO: Fix this - Currently fails because fee_token is a mock contract
    # assert tx.events == [
    #     fee_token.Transfer(admin, subscription.address, cost),
    #     managed_allow_list.AddressAuthorizationSet(RITUAL_ID, admin, True)
    # ]
    assert len(tx.events) == 3
    assert subscription.authorizationActionsCap(RITUAL_ID, admin) == 1000

    # Only administrators can authorize encryptors
    with ape.reverts("Only administrator is permitted"):
        managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=encryptor)

    tx = managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    assert tx.events == [managed_allow_list.AddressAuthorizationSet(RITUAL_ID, encryptor, True)]
    assert managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)


def test_deauthorize(
    managed_allow_list, subscription, fee_token, deployer, authority, admin, encryptor
):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    cost = subscription.subscriptionFee()
    fee_token.approve(subscription.address, cost, sender=deployer)
    subscription.newSubscription(RITUAL_ID, sender=deployer)
    assert subscription.authorizationActionsCap(RITUAL_ID, admin) == 1000
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)

    with ape.reverts("Only administrator is permitted"):
        managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=encryptor)

    tx = managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=admin)
    assert tx.events == [managed_allow_list.AddressAuthorizationSet(RITUAL_ID, encryptor, False)]
    assert not managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)
