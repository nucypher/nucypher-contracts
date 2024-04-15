import pytest

# Stuff copied from test_coordinator.py

TIMEOUT = 1000
MAX_DKG_SIZE = 31
FEE_RATE = 42
ERC20_SUPPLY = 10**24


@pytest.fixture(scope="module")
def nodes(accounts):
    return sorted(accounts[:MAX_DKG_SIZE], key=lambda x: x.address.lower())


@pytest.fixture(scope="module")
def initiator(accounts):
    initiator_index = MAX_DKG_SIZE + 1
    assert len(accounts) >= initiator_index
    return accounts[initiator_index]


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer_index = MAX_DKG_SIZE + 2
    assert len(accounts) >= deployer_index
    return accounts[deployer_index]


@pytest.fixture(scope="module")
def treasury(accounts):
    treasury_index = MAX_DKG_SIZE + 3
    assert len(accounts) >= treasury_index
    return accounts[treasury_index]


@pytest.fixture()
def application(project, deployer, nodes):
    contract = project.ChildApplicationForCoordinatorMock.deploy(sender=deployer)
    for n in nodes:
        contract.updateOperator(n, n, sender=deployer)
        contract.updateAuthorization(n, 42, sender=deployer)
    return contract


@pytest.fixture()
def erc20(project, initiator):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=initiator)
    return token


@pytest.fixture()
def coordinator(project, deployer, application, erc20, initiator, oz_dependency):
    contract = project.Coordinator.deploy(
        application.address,
        erc20.address,
        FEE_RATE,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(TIMEOUT, MAX_DKG_SIZE, deployer)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.Coordinator.at(proxy.address)

    proxy_contract.grantRole(contract.INITIATOR_ROLE(), initiator, sender=deployer)
    return proxy_contract


# My fixtures

RITUAL_ID = 1
ADMIN_CAP = 5


@pytest.fixture()
def authority(accounts):
    return accounts[1]


@pytest.fixture()
def admin(accounts):
    return accounts[2]


@pytest.fixture()
def encryptor(accounts):
    return accounts[3]


@pytest.fixture()
def managed_allow_list(project, coordinator, authority):
    return project.ManagedAllowList.deploy(coordinator.address, sender=authority)


def test_initial_parameters(managed_allow_list, coordinator, authority, admin, encryptor):
    assert managed_allow_list.coordinator() == coordinator.address
    assert not managed_allow_list.administrators(admin.address)
    assert not managed_allow_list.authorizations(encryptor.address)


def test_add_administrator(managed_allow_list, authority, admin):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    assert managed_allow_list.administrators(admin) == ADMIN_CAP


def test_remove_administrator(managed_allow_list, authority, admin):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=authority)
    assert not managed_allow_list.administrators(admin)


def test_authorize(managed_allow_list, authority, admin, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    assert managed_allow_list.authorizations(encryptor)


def test_deauthorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=admin)
    assert not managed_allow_list.authorizations(encryptor)


def test_only_authority_can_add_administrator(managed_allow_list, admin, authority, encryptor):
    with pytest.raises(Exception):
        managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=admin)
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], sender=authority)
    assert managed_allow_list.administrators(admin)


def test_only_authority_can_remove_administrator(managed_allow_list, admin, authority):
    managed_allow_list.addAdministrator(RITUAL_ID, admin, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=admin)
    managed_allow_list.removeAdministrators(RITUAL_ID, [admin], sender=authority)
    assert not managed_allow_list.administrators(admin)


def test_only_administrator_can_authorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=encryptor)
    managed_allow_list.authorize(RITUAL_ID, [encryptor], sender=admin)
    assert managed_allow_list.authorizations(admin)


def test_only_administrator_can_deauthorize(managed_allow_list, admin, authority, encryptor):
    managed_allow_list.addAdministrators(RITUAL_ID, [admin], ADMIN_CAP, sender=authority)
    with pytest.raises(Exception):
        managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=encryptor)
    managed_allow_list.deauthorize(RITUAL_ID, [encryptor], sender=admin)
    assert not managed_allow_list.authorizations(admin)
