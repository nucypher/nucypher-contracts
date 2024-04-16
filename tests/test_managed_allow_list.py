import pytest


RITUAL_ID = 0
ADMIN_CAP = 5


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


@pytest.fixture()
def coordinator(project, deployer):
    contract = project.CoordinatorForEncryptionAuthorizerMock.deploy(
        sender=deployer,
    )
    return contract


@pytest.fixture()
def brand_new_managed_allow_list(project, coordinator, authority):
    return project.ManagedAllowList.deploy(coordinator.address, sender=authority)


@pytest.fixture()
def managed_allow_list(brand_new_managed_allow_list, coordinator, deployer, authority):
    coordinator.mockNewRitual(authority, sender=deployer)
    return brand_new_managed_allow_list


def test_initial_parameters(brand_new_managed_allow_list, coordinator, admin, encryptor):
    assert brand_new_managed_allow_list.coordinator() == coordinator.address
    assert not brand_new_managed_allow_list.getAllowance(RITUAL_ID, admin.address)
    assert not brand_new_managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor.address)


# TODO: Missing checks for events below

def test_add_administrator(managed_allow_list, authority, admin):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    assert managed_allow_list.getAllowance(RITUAL_ID, admin) == ADMIN_CAP


def test_remove_administrator(managed_allow_list, authority, admin):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=authority)
    assert not managed_allow_list.getAllowance(RITUAL_ID, admin)


def test_authorize(managed_allow_list, authority, admin, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    assert managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)


def test_deauthorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=admin)
    assert not managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)


def test_only_authority_can_add_administrator(managed_allow_list, admin, authority, encryptor):
    with pytest.raises(Exception):
        managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=admin)
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    assert managed_allow_list.getAllowance(RITUAL_ID, admin)


def test_only_authority_can_remove_administrator(managed_allow_list, admin, authority):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=admin)
    managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=authority)
    assert not managed_allow_list.getAllowance(RITUAL_ID, admin)


def test_only_administrator_can_authorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=encryptor)
    with pytest.raises(Exception):
        managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=authority)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    assert managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)


def test_only_administrator_can_deauthorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=encryptor)
    with pytest.raises(Exception):
        managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=authority)
    managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=admin)
    assert not managed_allow_list.isAddressAuthorized(RITUAL_ID, encryptor)
