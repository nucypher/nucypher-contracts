import os
from enum import IntEnum

import ape
import pytest

from tests.conftest import generate_transcript

TIMEOUT = 1000
MAX_DKG_SIZE = 31
FEE_RATE = 42
ERC20_SUPPLY = 10**24
DURATION = 48 * 60 * 60
ONE_DAY = 24 * 60 * 60
# Period duration for PenaltyBoard: long enough that ritual timeout stays in period 0
PENALTY_BOARD_PERIOD_DURATION = 7 * ONE_DAY

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


@pytest.fixture(scope="module")
def informer(accounts):
    informer_index = MAX_DKG_SIZE + 4
    assert len(accounts) >= informer_index
    return accounts[informer_index]


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
def coordinator(project, deployer, application, oz_dependency):
    admin = deployer
    contract = project.Coordinator.deploy(
        application.address,
        TIMEOUT,
        0,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(MAX_DKG_SIZE, admin)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.Coordinator.at(proxy.address)
    return proxy_contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


@pytest.fixture()
def fee_model(project, deployer, coordinator, erc20, treasury):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, erc20.address, FEE_RATE, sender=deployer
    )
    coordinator.grantRole(coordinator.FEE_MODEL_MANAGER_ROLE(), treasury, sender=deployer)
    coordinator.approveFeeModel(contract.address, sender=treasury)
    return contract


@pytest.fixture
def infraction_collector(project, deployer, coordinator):
    contract = project.InfractionCollector.deploy(coordinator.address, sender=deployer)
    return contract


@pytest.fixture
def penalty_board(project, deployer, informer, chain):
    """PenaltyBoard with genesis at current chain time and INFORMER_ROLE granted to informer.
    Period duration is one week so ritual timeout still lands in period 0. No compensation."""
    genesis_time = chain.pending_timestamp
    zero = "0x0000000000000000000000000000000000000000"
    contract = project.PenaltyBoard.deploy(
        genesis_time,
        PENALTY_BOARD_PERIOD_DURATION,
        deployer.address,
        zero,
        zero,
        0,
        zero,
        sender=deployer,
    )
    contract.grantRole(contract.INFORMER_ROLE(), informer.address, sender=deployer)
    return contract


def test_no_infractions(
    erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, fee_model
):
    cost = fee_model.getRitualCost(len(nodes), DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(fee_model.address, cost, sender=initiator)
    coordinator.initiateRitual(
        fee_model, nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)
    
    for node in nodes:
        coordinator.publishTranscript(0, transcript, sender=node)

    with ape.reverts("Ritual must have failed"):
        infraction_collector.reportMissingTranscript(0, nodes, sender=initiator)


def test_partial_infractions(
    erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain, fee_model
):
    cost = fee_model.getRitualCost(len(nodes), DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(fee_model.address, cost, sender=initiator)
    coordinator.initiateRitual(
        fee_model, nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    # post transcript for half of nodes
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)
    for node in nodes[: len(nodes) // 2]:
        coordinator.publishTranscript(RITUAL_ID, transcript, sender=node)
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(
        RITUAL_ID, nodes[len(nodes) // 2 :], sender=initiator
    )
    # first half of nodes should be fine, second half should be infracted
    for node in nodes[: len(nodes) // 2]:
        assert not infraction_collector.infractionsForRitual(
            RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT
        )
    for node in nodes[len(nodes) // 2 :]:
        assert infraction_collector.infractionsForRitual(
            RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT
        )


def test_report_infractions(
    erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain, fee_model
):
    cost = fee_model.getRitualCost(len(nodes), DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(fee_model.address, cost, sender=initiator)
    coordinator.initiateRitual(
        fee_model, nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)
    for node in nodes:
        assert infraction_collector.infractionsForRitual(
            RITUAL_ID, node, infraction_types.MISSING_TRANSCRIPT
        )


def test_cant_report_infractions_twice(
    erc20, nodes, initiator, global_allow_list, infraction_collector, coordinator, chain, fee_model
):
    cost = fee_model.getRitualCost(len(nodes), DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(fee_model.address, cost, sender=initiator)
    coordinator.initiateRitual(
        fee_model, nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    chain.pending_timestamp += TIMEOUT * 2
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)

    with ape.reverts("Infraction already reported"):
        infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)


def test_infraction_collector_and_penalty_board_together(
    erc20,
    nodes,
    initiator,
    global_allow_list,
    infraction_collector,
    coordinator,
    chain,
    fee_model,
    penalty_board,
    informer,
):
    """Use InfractionCollector (ritual-level infractions) and PenaltyBoard (period-level penalties) together.
    No on-chain link: informer sets penalized providers on PenaltyBoard from the same addresses that were
    reported to InfractionCollector."""
    cost = fee_model.getRitualCost(len(nodes), DURATION)
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    erc20.approve(fee_model.address, cost, sender=initiator)
    coordinator.initiateRitual(
        fee_model, nodes, initiator, DURATION, global_allow_list.address, sender=initiator
    )
    # No transcripts published; ritual times out
    chain.pending_timestamp += TIMEOUT * 2
    failing_providers = [n.address for n in nodes]
    infraction_collector.reportMissingTranscript(RITUAL_ID, nodes, sender=initiator)

    # Same period still (period duration is 1 week; we advanced ~2000s). Informer records
    # penalized providers for this period on PenaltyBoard.
    current_period = penalty_board.getCurrentPeriod()
    penalty_board.setPenalizedProvidersForPeriod(
        failing_providers, current_period, sender=informer
    )
    for provider in failing_providers:
        periods = penalty_board.getPenalizedPeriodsByStaker(provider)
        assert periods == [current_period]
