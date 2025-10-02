import os

import ape
import pytest
from ape.utils import ZERO_ADDRESS
from web3 import Web3

from tests.conftest import G1_SIZE, G2_SIZE, HandoverState, gen_public_key, generate_transcript

TIMEOUT = 1000
MAX_DKG_SIZE = 31
FEE_RATE = 42
ERC20_SUPPLY = 10**24
DURATION = 48 * 60 * 60
HANDOVER_TIMEOUT = 2000


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
def coordinator(project, deployer, application, oz_dependency):
    admin = deployer
    contract = project.Coordinator.deploy(
        application.address,
        TIMEOUT,
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
def handover_coordinator(project, deployer, application, coordinator, oz_dependency):
    admin = deployer
    contract = project.HandoverCoordinator.deploy(
        application.address,
        coordinator.address,
        HANDOVER_TIMEOUT,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(admin)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.HandoverCoordinator.at(proxy.address)
    coordinator.initializeHandoverCoordinator(proxy.address, sender=deployer)
    return proxy_contract


@pytest.fixture()
def fee_model(project, deployer, coordinator, erc20, treasury):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, erc20.address, FEE_RATE, sender=deployer
    )
    coordinator.grantRole(coordinator.FEE_MODEL_MANAGER_ROLE(), treasury, sender=deployer)
    coordinator.approveFeeModel(contract.address, sender=treasury)
    coordinator.grantRole(coordinator.FEE_MODEL_MANAGER_ROLE(), treasury, sender=deployer)
    return contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


def test_initial_parameters(handover_coordinator):
    assert handover_coordinator.handoverTimeout() == HANDOVER_TIMEOUT


def initiate_ritual(coordinator, fee_model, erc20, authority, nodes, allow_logic):
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)

    cost = fee_model.getRitualCost(len(nodes), DURATION)
    erc20.approve(fee_model.address, cost, sender=authority)
    tx = coordinator.initiateRitual(
        fee_model, nodes, authority, DURATION, allow_logic.address, sender=authority
    )
    return authority, tx


def activate_ritual(nodes, coordinator, ritualID):
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        coordinator.publishTranscript(ritualID, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        coordinator.postAggregation(
            ritualID, aggregated, dkg_public_key, decryption_request_static_keys[i], sender=node
        )
    return threshold, aggregated


def setup_node(node, coordinator, application, deployer):
    application.updateOperator(node, node, sender=deployer)
    application.updateAuthorization(node, 42, sender=deployer)
    public_key = gen_public_key()
    coordinator.setProviderPublicKey(public_key, sender=node)


def test_handover_request(
    coordinator,
    handover_coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    accounts,
    deployer,
    global_allow_list,
    application,
    chain,
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    departing_node = nodes[10]
    incoming_node = accounts[MAX_DKG_SIZE + 1]
    handover_supervisor = accounts[MAX_DKG_SIZE]

    handover_coordinator.grantRole(
        handover_coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    with ape.reverts():
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=deployer
        )

    with ape.reverts("Ritual is not active"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    activate_ritual(nodes, coordinator, ritualID)

    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )

    with ape.reverts("Departing node must be a participant"):
        handover_coordinator.handoverRequest(
            ritualID, handover_supervisor, incoming_node, sender=handover_supervisor
        )
    with ape.reverts("Incoming node cannot be a participant"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, nodes[0], sender=handover_supervisor
        )
    with ape.reverts("Incoming provider has not set public key"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    setup_node(incoming_node, coordinator, application, deployer)

    tx = handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )

    timestamp = chain.pending_timestamp - 1
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == timestamp
    assert handover.incomingProvider == incoming_node
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverRequest"]
    assert events == [
        handover_coordinator.HandoverRequest(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    with ape.reverts("Handover already requested"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )
    handover_coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )

    with ape.reverts("Handover already requested"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    handover_coordinator.postBlindedShare(ritualID, os.urandom(G2_SIZE), sender=departing_node)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )

    with ape.reverts("Handover already requested"):
        handover_coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_TIMEOUT
    )

    incoming_node = accounts[MAX_DKG_SIZE + 2]
    setup_node(incoming_node, coordinator, application, deployer)

    tx = handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )

    timestamp = chain.pending_timestamp - 1
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == timestamp
    assert handover.incomingProvider == incoming_node
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverRequest"]
    assert events == [
        handover_coordinator.HandoverRequest(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]


def test_post_handover_transcript(
    coordinator,
    handover_coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    accounts,
    deployer,
    global_allow_list,
    application,
    chain,
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    departing_node = nodes[10]
    incoming_node = accounts[MAX_DKG_SIZE + 1]
    handover_supervisor = accounts[MAX_DKG_SIZE]
    decryption_request_static_key = os.urandom(42)
    handover_transcript = os.urandom(42)

    with ape.reverts("Ritual is not active"):
        handover_coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    handover_coordinator.grantRole(
        handover_coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Parameters can't be empty"):
        handover_coordinator.postHandoverTranscript(
            ritualID, departing_node, bytes(), decryption_request_static_key, sender=incoming_node
        )

    with ape.reverts("Invalid length for decryption request static key"):
        handover_coordinator.postHandoverTranscript(
            ritualID, departing_node, handover_transcript, os.urandom(41), sender=incoming_node
        )

    with ape.reverts("Not waiting for transcript"):
        handover_coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )

    with ape.reverts("Wrong incoming provider"):
        handover_coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=departing_node,
        )

    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )
    tx = handover_coordinator.postHandoverTranscript(
        ritualID,
        departing_node,
        handover_transcript,
        decryption_request_static_key,
        sender=incoming_node,
    )
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE
    )
    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.incomingProvider == incoming_node
    assert handover.transcript == handover_transcript
    assert handover.decryptionRequestStaticKey == decryption_request_static_key

    events = [event for event in tx.events if event.event_name == "HandoverTranscriptPosted"]
    assert events == [
        handover_coordinator.HandoverTranscriptPosted(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    with ape.reverts("Not waiting for transcript"):
        handover_coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_TIMEOUT
    )

    with ape.reverts("Not waiting for transcript"):
        handover_coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )


def test_post_blinded_share(
    coordinator,
    handover_coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    accounts,
    deployer,
    global_allow_list,
    application,
    chain,
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    departing_node = nodes[10]
    incoming_node = accounts[MAX_DKG_SIZE + 1]
    handover_supervisor = accounts[MAX_DKG_SIZE]
    blinded_share = os.urandom(G2_SIZE)

    with ape.reverts("Ritual is not active"):
        handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    handover_coordinator.grantRole(
        handover_coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Not waiting for blinded share"):
        handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )

    with ape.reverts("Not waiting for blinded share"):
        handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    handover_coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )

    with ape.reverts("Wrong size of blinded share"):
        handover_coordinator.postBlindedShare(ritualID, os.urandom(16), sender=departing_node)

    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE
    )
    tx = handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )
    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.incomingProvider == incoming_node
    assert handover.blindedShare == blinded_share
    assert len(handover.transcript) != 0
    assert len(handover.decryptionRequestStaticKey) != 0

    events = [event for event in tx.events if event.event_name == "BlindedSharePosted"]
    assert events == [
        handover_coordinator.BlindedSharePosted(
            ritualId=ritualID, departingParticipant=departing_node
        )
    ]

    with ape.reverts("Not waiting for blinded share"):
        handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_TIMEOUT
    )

    with ape.reverts("Not waiting for blinded share"):
        handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)


def test_cancel_handover(
    coordinator,
    handover_coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    accounts,
    deployer,
    global_allow_list,
    application,
    chain,
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    departing_node = nodes[10]
    incoming_node = accounts[MAX_DKG_SIZE + 1]
    handover_supervisor = accounts[MAX_DKG_SIZE]
    blinded_share = os.urandom(G2_SIZE)

    with ape.reverts():
        handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    handover_coordinator.grantRole(
        handover_coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    with ape.reverts("Handover not requested"):
        handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Handover not requested"):
        handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )

    tx = handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )

    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverCanceled"]
    assert events == [
        handover_coordinator.HandoverCanceled(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    handover_coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )
    handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    handover_coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )
    handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    tx = handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )

    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverCanceled"]
    assert events == [
        handover_coordinator.HandoverCanceled(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    chain.pending_timestamp += HANDOVER_TIMEOUT + 1
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_TIMEOUT
    )
    handover_coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )


@pytest.mark.parametrize("participant_index", range(0, MAX_DKG_SIZE, 2))
def test_finalize_handover(
    coordinator,
    handover_coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    accounts,
    deployer,
    global_allow_list,
    application,
    participant_index,
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    departing_node = nodes[participant_index]
    incoming_node = accounts[MAX_DKG_SIZE + 1]
    handover_supervisor = accounts[MAX_DKG_SIZE]
    blinded_share = os.urandom(G2_SIZE)

    with ape.reverts():
        handover_coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    handover_coordinator.grantRole(
        handover_coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    threshold, aggregated = activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Not waiting for finalization"):
        handover_coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    handover_coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )

    with ape.reverts("Not waiting for finalization"):
        handover_coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)
    decryption_request_static_key = os.urandom(42)
    handover_coordinator.postHandoverTranscript(
        ritualID,
        departing_node,
        os.urandom(42),
        decryption_request_static_key,
        sender=incoming_node,
    )

    with ape.reverts("Not waiting for finalization"):
        handover_coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    handover_coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )

    assert not application.stakingProviderReleased(departing_node)
    tx = handover_coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)
    assert (
        handover_coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.NON_INITIATED
    )
    assert application.stakingProviderReleased(departing_node)

    events = [event for event in tx.events if event.event_name == "HandoverFinalized"]
    assert events == [
        handover_coordinator.HandoverFinalized(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    handover_key = handover_coordinator.getHandoverKey(ritualID, departing_node)
    handover = handover_coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    with ape.reverts("Participant not part of ritual"):
        coordinator.getParticipantFromProvider(ritualID, departing_node)

    p = coordinator.getParticipantFromProvider(ritualID, incoming_node)
    assert p.provider == incoming_node
    assert p.aggregated is True
    assert len(p.transcript) == 0
    assert p.decryptionRequestStaticKey == decryption_request_static_key

    index = 32 + participant_index * G2_SIZE + threshold * G1_SIZE
    aggregated = bytearray(aggregated)
    aggregated[index : index + G2_SIZE] = blinded_share
    aggregated = bytes(aggregated)
    assert coordinator.rituals(ritualID).aggregatedTranscript == aggregated

    events = [event for event in tx.events if event.event_name == "AggregationPosted"]
    assert events == [
        coordinator.AggregationPosted(
            ritualId=ritualID,
            node=incoming_node,
            aggregatedTranscriptDigest=Web3.keccak(aggregated),
        )
    ]
