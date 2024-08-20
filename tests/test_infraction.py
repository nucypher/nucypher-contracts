import os
from enum import IntEnum

import ape
import pytest

TIMEOUT = 1000
MAX_DKG_SIZE = 31
FEE_RATE = 42
ERC20_SUPPLY = 10**24
DURATION = 48 * 60 * 60
ONE_DAY = 24 * 60 * 60

RITUAL_ID = 0

infraction_types = IntEnum(
    "InfractionType",
    [
        "MISSING_TRANSCRIPT",
    ],
    start=0,
)


# This formula returns an approximated size
# To have a representative size, create transcripts with `nucypher-core`
def transcript_size(shares, threshold):
    return int(424 + 240 * (shares / 2) + 50 * (threshold))


def gen_public_key():
    return (os.urandom(32), os.urandom(32), os.urandom(32))


def access_control_error_message(address, role=None):
    role = role or b"\x00" * 32
    return f"account={address}, neededRole={role}"


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
    admin = deployer
    contract = project.Coordinator.deploy(
        application.address,
        erc20.address,
        FEE_RATE,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(TIMEOUT, MAX_DKG_SIZE, admin)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.Coordinator.at(proxy.address)

    proxy_contract.grantRole(contract.INITIATOR_ROLE(), initiator, sender=admin)
    return proxy_contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


@pytest.fixture
def infraction_collector(project, deployer, coordinator):
    contract = project.InfractionCollector.deploy(coordinator.address, sender=deployer)
    return contract

def test_no_infractions(erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator):
    cost = coordinator.getRitualInitiationCost(nodes, DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)  
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(
        nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    with ape.reverts("Ritual must have failed"):
        infraction_collector.reportMissingTranscript(0, nodes, sender=initiator)

def test_partial_infractions(erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain):
    cost = coordinator.getRitualInitiationCost(nodes, DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(
        nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    # post transcript for half of nodes
    for node in nodes[:len(nodes) // 2]:
        coordinator.postTranscript(RITUAL_ID, transcript, sender=node)
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes[len(nodes) // 2:], sender=initiator)
    # first half of nodes should be fine, second half should be infracted
    for node in nodes[:len(nodes) // 2]:
        assert not infraction_collector.infractionsForRitual(RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT)
    for node in nodes[len(nodes) // 2:]:
        assert infraction_collector.infractionsForRitual(RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT)

def test_report_infractions(erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain):
    cost = coordinator.getRitualInitiationCost(nodes, DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)   
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(
        nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)
    for node in nodes:
        assert infraction_collector.infractionsForRitual(RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT)

def test_cant_report_infractions_twice(erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain):
    cost = coordinator.getRitualInitiationCost(nodes, DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)   
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(
        nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)
    
    with ape.reverts("Infraction already reported"):
        infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)