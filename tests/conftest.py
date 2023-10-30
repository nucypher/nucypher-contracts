import pytest
from ape import convert, project


@pytest.fixture(scope="session")
def oz_dependency():
    return project.dependencies["openzeppelin"]["5.0.0"]


@pytest.fixture
def creator(accounts):
    return accounts[0]


@pytest.fixture
def account1(accounts):
    return accounts[1]


@pytest.fixture
def account2(accounts):
    return accounts[2]


@pytest.fixture
def nu_token(NuCypherToken, creator):
    TOTAL_SUPPLY = convert("1_000_000_000 ether", int)
    nu_token = creator.deploy(NuCypherToken, TOTAL_SUPPLY)
    return nu_token
