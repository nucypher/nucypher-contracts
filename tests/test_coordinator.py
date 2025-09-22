import os

import ape
import pytest
from ape.utils import ZERO_ADDRESS
from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3

from tests.conftest import (
    G1_SIZE,
    G2_SIZE,
    HandoverState,
    RitualState,
    gen_public_key,
    generate_transcript,
)

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
        HANDOVER_TIMEOUT,
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
def fee_model(project, deployer, coordinator, erc20, treasury):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, erc20.address, FEE_RATE, sender=deployer
    )
    coordinator.grantRole(coordinator.FEE_MODEL_MANAGER_ROLE(), treasury, sender=deployer)
    coordinator.approveFeeModel(contract.address, sender=treasury)
    coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
    return contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.dkgTimeout() == TIMEOUT
    assert coordinator.handoverTimeout() == HANDOVER_TIMEOUT
    assert coordinator.numberOfRituals() == 0


def test_invalid_initiate_ritual(
    project, coordinator, nodes, accounts, initiator, fee_model, global_allow_list
):
    with ape.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(
            fee_model.address,
            nodes[:5] * 20,
            initiator,
            DURATION,
            global_allow_list.address,
            sender=initiator,
        )

    with ape.reverts("Invalid ritual duration"):
        coordinator.initiateRitual(
            fee_model.address, nodes, initiator, 0, global_allow_list.address, sender=initiator
        )

    with ape.reverts("Provider has not set their public key"):
        coordinator.initiateRitual(
            fee_model.address,
            nodes,
            initiator,
            DURATION,
            global_allow_list.address,
            sender=initiator,
        )

    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)

    with ape.reverts("Providers must be sorted"):
        coordinator.initiateRitual(
            fee_model.address,
            nodes[1:] + [nodes[0]],
            initiator,
            DURATION,
            global_allow_list.address,
            sender=initiator,
        )

    with ape.reverts(project.TestToken.ERC20InsufficientAllowance):
        # Sender didn't approve enough tokens
        coordinator.initiateRitual(
            fee_model.address,
            nodes,
            initiator,
            DURATION,
            global_allow_list.address,
            sender=initiator,
        )


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


def test_initiate_ritual(
    coordinator, nodes, initiator, erc20, fee_model, deployer, treasury, global_allow_list
):
    authority, tx = initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    events = [event for event in tx.events if event.event_name == "StartRitual"]
    assert len(events) == 1
    event = events[0]
    assert event.ritualId == ritualID
    assert event.authority == authority
    assert event.participants == [n.address for n in nodes]

    assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_TRANSCRIPTS

    ritual_struct = coordinator.rituals(ritualID)
    assert ritual_struct[0] == initiator
    init, end = ritual_struct[1], ritual_struct["endTimestamp"]
    assert end - init == DURATION
    total_transcripts, total_aggregations = (
        ritual_struct["totalTranscripts"],
        ritual_struct["totalAggregations"],
    )
    assert total_transcripts == total_aggregations == 0
    assert ritual_struct["authority"] == authority
    assert ritual_struct["dkgSize"] == len(nodes)
    assert ritual_struct["threshold"] == 1 + len(nodes) // 2  # threshold
    assert not ritual_struct["aggregationMismatch"]  # aggregationMismatch
    assert ritual_struct["accessController"] == global_allow_list.address  # accessController
    assert ritual_struct["publicKey"] == (b"\x00" * 32, b"\x00" * 16)  # publicKey
    assert not ritual_struct["aggregatedTranscript"]  # aggregatedTranscript

    fee = fee_model.getRitualCost(len(nodes), DURATION)
    assert erc20.balanceOf(fee_model) == fee
    assert fee_model.totalPendingFees() == fee
    assert fee_model.pendingFees(ritualID) == fee

    with ape.reverts():
        fee_model.withdrawTokens(1, sender=treasury)

    with ape.reverts("Can't withdraw pending fees"):
        fee_model.withdrawTokens(1, sender=deployer)


def test_provider_public_key(coordinator, nodes):
    selected_provider = nodes[0]
    public_key = gen_public_key()

    assert not coordinator.isProviderKeySet(selected_provider)
    tx = coordinator.setProviderPublicKey(public_key, sender=selected_provider)
    assert coordinator.isProviderKeySet(selected_provider)

    # with ape.reverts("Deprecated method. Upgrade your node to latest version"):
    #     coordinator.isProviderPublicKeySet(selected_provider)

    ritual_id = coordinator.numberOfRituals()

    events = [event for event in tx.events if event.event_name == "ParticipantPublicKeySet"]
    assert len(events) == 1
    event = events[0]
    assert event.ritualId == ritual_id
    assert event.participant == selected_provider
    assert event.publicKey == [HexBytes(k) for k in public_key]
    assert coordinator.getProviderPublicKey(selected_provider, ritual_id) == public_key


def test_post_transcript(coordinator, nodes, initiator, erc20, fee_model, global_allow_list):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_TRANSCRIPTS

        tx = coordinator.publishTranscript(0, transcript, sender=node)

        events = [event for event in tx.events if event.event_name == "TranscriptPosted"]
        assert events == [
            coordinator.TranscriptPosted(
                ritualId=0, node=node, transcriptDigest=Web3.keccak(transcript)
            )
        ]

    participants = coordinator.getParticipants(0)
    for participant in participants:
        assert not participant.aggregated
        assert not participant.decryptionRequestStaticKey

    assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_AGGREGATIONS


def test_post_transcript_but_not_part_of_ritual(
    coordinator, nodes, initiator, erc20, fee_model, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    with ape.reverts("Participant not part of ritual"):
        coordinator.publishTranscript(0, transcript, sender=initiator)


def test_post_transcript_but_already_posted_transcript(
    coordinator, nodes, initiator, erc20, fee_model, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    coordinator.publishTranscript(0, transcript, sender=nodes[0])
    with ape.reverts("Node already posted transcript"):
        coordinator.publishTranscript(0, transcript, sender=nodes[0])


def test_post_transcript_but_wrong_size(
    coordinator, nodes, initiator, erc20, fee_model, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    bad_transcript = generate_transcript(size, threshold + 1)

    with ape.reverts("Invalid transcript size"):
        coordinator.publishTranscript(0, bad_transcript, sender=nodes[0])

    bad_transcript = b""
    with ape.reverts("Invalid transcript size"):
        coordinator.publishTranscript(0, bad_transcript, sender=nodes[0])


def test_post_transcript_but_not_waiting_for_transcripts(
    coordinator, nodes, initiator, erc20, fee_model, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        coordinator.publishTranscript(0, transcript, sender=node)

    with ape.reverts("Not waiting for transcripts"):
        coordinator.publishTranscript(0, transcript, sender=nodes[1])


def test_get_participants(coordinator, nodes, initiator, erc20, fee_model, global_allow_list):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        _ = coordinator.publishTranscript(0, transcript, sender=node)

    # get all participants
    participants = coordinator.getParticipants(0, 0, len(nodes), False)
    assert len(participants) == len(nodes)
    for index, participant in enumerate(participants):
        assert participant.provider == nodes[index].address
        assert participant.aggregated is False
        assert not participant.transcript

    # max is higher than available
    participants = coordinator.getParticipants(0, 0, len(nodes) * 2, False)
    assert len(participants) == len(nodes)
    for index, participant in enumerate(participants):
        assert participant.provider == nodes[index].address
        assert participant.aggregated is False
        assert not participant.transcript

    # max is 0 which means get all
    participants = coordinator.getParticipants(0, 0, 0, True)
    assert len(participants) == len(nodes)
    for index, participant in enumerate(participants):
        assert participant.provider == nodes[index].address
        assert participant.aggregated is False
        assert participant.transcript == transcript

    # n at a time
    for n_at_a_time in range(2, len(nodes) // 2):
        index = 0
        while index < len(nodes):
            participants_n_at_a_time = coordinator.getParticipants(0, index, n_at_a_time, True)
            assert len(participants_n_at_a_time) <= n_at_a_time
            for i, participant in enumerate(participants_n_at_a_time):
                assert participant.provider == nodes[index + i].address
                assert participant.aggregated is False
                assert participant.transcript == transcript

            index += len(participants_n_at_a_time)

        assert index == len(nodes)


def test_get_participant(nodes, coordinator, initiator, erc20, fee_model, global_allow_list):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        _ = coordinator.publishTranscript(0, transcript, sender=node)

    # find actual participants
    for i, node in enumerate(nodes):
        p = coordinator.getParticipant(0, node.address, True)
        assert p.provider == node.address
        assert p.aggregated is False
        assert p.transcript == transcript

        p = coordinator.getParticipant(0, node.address, False)
        assert p.provider == node.address
        assert p.aggregated is False
        assert not p.transcript

        p = coordinator.getParticipantFromProvider(0, node.address)
        assert p.provider == node.address
        assert p.aggregated is False
        assert p.transcript == transcript

    # can't find non-participants
    for i in range(5):
        while True:
            new_account = Account.create()
            if new_account.address not in nodes:
                break
        with ape.reverts("Participant not part of ritual"):
            coordinator.getParticipant(0, new_account.address, True)

        with ape.reverts("Participant not part of ritual"):
            coordinator.getParticipant(0, new_account.address, False)

        with ape.reverts("Participant not part of ritual"):
            coordinator.getParticipantFromProvider(0, new_account.address)


def test_post_aggregation(
    coordinator, nodes, initiator, erc20, fee_model, treasury, deployer, global_allow_list
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
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        coordinator.publishTranscript(ritualID, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(ritualID) == RitualState.DKG_AWAITING_AGGREGATIONS
        tx = coordinator.postAggregation(
            ritualID, aggregated, dkg_public_key, decryption_request_static_keys[i], sender=node
        )

        events = [event for event in tx.events if event.event_name == "AggregationPosted"]
        assert events == [
            coordinator.AggregationPosted(
                ritualId=ritualID, node=node, aggregatedTranscriptDigest=Web3.keccak(aggregated)
            )
        ]

    participants = coordinator.getParticipants(ritualID)
    for i, participant in enumerate(participants):
        assert participant.aggregated
        assert participant.decryptionRequestStaticKey == decryption_request_static_keys[i]

    assert coordinator.getRitualState(ritualID) == RitualState.ACTIVE
    events = [event for event in tx.events if event.event_name == "EndRitual"]
    assert events == [coordinator.EndRitual(ritualId=ritualID, successful=True)]

    retrieved_public_key = coordinator.getPublicKeyFromRitualId(ritualID)
    assert retrieved_public_key == dkg_public_key
    assert coordinator.getRitualIdFromPublicKey(dkg_public_key) == ritualID

    fee_model.processPendingFee(ritualID, sender=treasury)
    fee = fee_model.getRitualCost(len(nodes), DURATION)
    assert erc20.balanceOf(fee_model) == fee
    assert fee_model.totalPendingFees() == 0
    assert fee_model.pendingFees(ritualID) == 0

    with ape.reverts("Can't withdraw pending fees"):
        fee_model.withdrawTokens(fee + 1, sender=deployer)
    fee_model.withdrawTokens(fee, sender=deployer)


def test_post_aggregation_fails(
    coordinator, nodes, initiator, erc20, fee_model, treasury, deployer, global_allow_list
):
    initiator_balance_before_payment = erc20.balanceOf(initiator)

    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    size = len(nodes)
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)

    for node in nodes:
        coordinator.publishTranscript(ritualID, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))

    # First node does their thing
    _ = coordinator.postAggregation(
        ritualID, aggregated, dkg_public_key, decryption_request_static_keys[0], sender=nodes[0]
    )

    # Second node screws up everything
    bad_aggregated = generate_transcript(size, threshold)
    tx = coordinator.postAggregation(
        ritualID, bad_aggregated, dkg_public_key, decryption_request_static_keys[1], sender=nodes[1]
    )

    assert coordinator.getRitualState(ritualID) == RitualState.DKG_INVALID
    events = [event for event in tx.events if event.event_name == "EndRitual"]
    assert events == [coordinator.EndRitual(ritualId=ritualID, successful=False)]

    # Fees are still pending
    fee = fee_model.getRitualCost(len(nodes), DURATION)
    assert erc20.balanceOf(fee_model) == fee
    assert fee_model.totalPendingFees() == fee
    pending_fee = fee_model.pendingFees(ritualID)
    assert pending_fee == fee
    with ape.reverts("Can't withdraw pending fees"):
        fee_model.withdrawTokens(1, sender=deployer)

    # Anyone can trigger processing of pending fees

    initiator_balance_before_refund = erc20.balanceOf(initiator)
    assert initiator_balance_before_refund == initiator_balance_before_payment - fee

    fee_model.processPendingFee(ritualID, sender=treasury)

    initiator_balance_after_refund = erc20.balanceOf(initiator)
    fee_model_balance_after_refund = erc20.balanceOf(fee_model)
    refund = initiator_balance_after_refund - initiator_balance_before_refund
    assert refund == fee - fee_model.feeDeduction(pending_fee, DURATION)
    assert fee_model_balance_after_refund + refund == fee
    assert fee_model.totalPendingFees() == 0
    assert fee_model.pendingFees(ritualID) == 0
    fee_model.withdrawTokens(fee_model_balance_after_refund, sender=deployer)


# def test_withdraw_tokens(coordinator, initiator, erc20, treasury, deployer):
#     # Let's send some tokens to Coordinator by mistake
#     erc20.transfer(coordinator.address, 42, sender=initiator)
#     assert erc20.balanceOf(coordinator.address) == 42

#     # Only accounts with TREASURY_ROLE can withdraw
#     with ape.reverts():
#         coordinator.withdrawAllTokens(erc20.address, sender=treasury)

#     # Treasury is granted proper role and withdraws all tokens
#     treasury_balance_before = erc20.balanceOf(treasury.address)

#     coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
#     coordinator.withdrawAllTokens(erc20.address, sender=treasury)

#     assert erc20.balanceOf(coordinator.address) == 0
#     assert erc20.balanceOf(treasury.address) == 42 + treasury_balance_before

#     # Can't withdraw when there's no tokens
#     with ape.reverts("Insufficient balance"):
#         coordinator.withdrawAllTokens(erc20.address, sender=treasury)


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


@pytest.mark.skip(reason="temp")
def test_handover_request(
    coordinator,
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

    coordinator.grantRole(
        coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    with ape.reverts():
        coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=deployer)

    with ape.reverts("Ritual is not active"):
        coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    activate_ritual(nodes, coordinator, ritualID)

    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED

    with ape.reverts("Departing node must be a participant"):
        coordinator.handoverRequest(
            ritualID, handover_supervisor, incoming_node, sender=handover_supervisor
        )
    with ape.reverts("Incoming node cannot be a participant"):
        coordinator.handoverRequest(ritualID, departing_node, nodes[0], sender=handover_supervisor)
    with ape.reverts("Incoming provider has not set public key"):
        coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    setup_node(incoming_node, coordinator, application, deployer)

    tx = coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )

    timestamp = chain.pending_timestamp - 1
    handover = coordinator.handovers(handover_key)
    assert handover.requestTimestamp == timestamp
    assert handover.incomingProvider == incoming_node
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverRequest"]
    assert events == [
        coordinator.HandoverRequest(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    with ape.reverts("Handover already requested"):
        coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )
    coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )

    with ape.reverts("Handover already requested"):
        coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    coordinator.postBlindedShare(ritualID, os.urandom(G2_SIZE), sender=departing_node)
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )

    with ape.reverts("Handover already requested"):
        coordinator.handoverRequest(
            ritualID, departing_node, incoming_node, sender=handover_supervisor
        )

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.HANDOVER_TIMEOUT

    incoming_node = accounts[MAX_DKG_SIZE + 2]
    setup_node(incoming_node, coordinator, application, deployer)

    tx = coordinator.handoverRequest(
        ritualID, departing_node, incoming_node, sender=handover_supervisor
    )
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )

    timestamp = chain.pending_timestamp - 1
    handover = coordinator.handovers(handover_key)
    assert handover.requestTimestamp == timestamp
    assert handover.incomingProvider == incoming_node
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverRequest"]
    assert events == [
        coordinator.HandoverRequest(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]


@pytest.mark.skip(reason="temp")
def test_post_handover_transcript(
    coordinator,
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
        coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    coordinator.grantRole(
        coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Parameters can't be empty"):
        coordinator.postHandoverTranscript(
            ritualID, departing_node, bytes(), decryption_request_static_key, sender=incoming_node
        )

    with ape.reverts("Invalid length for decryption request static key"):
        coordinator.postHandoverTranscript(
            ritualID, departing_node, handover_transcript, os.urandom(41), sender=incoming_node
        )

    with ape.reverts("Not waiting for transcript"):
        coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)

    with ape.reverts("Wrong incoming provider"):
        coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=departing_node,
        )

    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_TRANSCRIPT
    )
    tx = coordinator.postHandoverTranscript(
        ritualID,
        departing_node,
        handover_transcript,
        decryption_request_static_key,
        sender=incoming_node,
    )
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE
    )
    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
    assert handover.incomingProvider == incoming_node
    assert handover.transcript == handover_transcript
    assert handover.decryptionRequestStaticKey == decryption_request_static_key

    events = [event for event in tx.events if event.event_name == "HandoverTranscriptPosted"]
    assert events == [
        coordinator.HandoverTranscriptPosted(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    with ape.reverts("Not waiting for transcript"):
        coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.HANDOVER_TIMEOUT

    with ape.reverts("Not waiting for transcript"):
        coordinator.postHandoverTranscript(
            ritualID,
            departing_node,
            handover_transcript,
            decryption_request_static_key,
            sender=incoming_node,
        )


@pytest.mark.skip(reason="temp")
def test_post_blinded_share(
    coordinator,
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
        coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    coordinator.grantRole(
        coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Not waiting for blinded share"):
        coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)

    with ape.reverts("Not waiting for blinded share"):
        coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )

    with ape.reverts("Wrong size of blinded share"):
        coordinator.postBlindedShare(ritualID, os.urandom(16), sender=departing_node)

    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE
    )
    tx = coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )
    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
    assert handover.incomingProvider == incoming_node
    assert handover.blindedShare == blinded_share
    assert len(handover.transcript) != 0
    assert len(handover.decryptionRequestStaticKey) != 0

    events = [event for event in tx.events if event.event_name == "BlindedSharePosted"]
    assert events == [
        coordinator.BlindedSharePosted(ritualId=ritualID, departingParticipant=departing_node)
    ]

    with ape.reverts("Not waiting for blinded share"):
        coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    chain.pending_timestamp += HANDOVER_TIMEOUT
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.HANDOVER_TIMEOUT

    with ape.reverts("Not waiting for blinded share"):
        coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)


@pytest.mark.skip(reason="temp")
def test_cancel_handover(
    coordinator,
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
        coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    coordinator.grantRole(
        coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    with ape.reverts("Handover not requested"):
        coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Handover not requested"):
        coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)

    tx = coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED

    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverCanceled"]
    assert events == [
        coordinator.HandoverCanceled(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)
    coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )
    coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)
    coordinator.postHandoverTranscript(
        ritualID, departing_node, os.urandom(42), os.urandom(42), sender=incoming_node
    )
    coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)

    tx = coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED

    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
    assert handover.requestTimestamp == 0
    assert handover.incomingProvider == ZERO_ADDRESS
    assert len(handover.blindedShare) == 0
    assert len(handover.transcript) == 0
    assert len(handover.decryptionRequestStaticKey) == 0

    events = [event for event in tx.events if event.event_name == "HandoverCanceled"]
    assert events == [
        coordinator.HandoverCanceled(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)
    chain.pending_timestamp += HANDOVER_TIMEOUT + 1
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.HANDOVER_TIMEOUT
    coordinator.cancelHandover(ritualID, departing_node, sender=handover_supervisor)
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED


@pytest.mark.skip(reason="temp")
@pytest.mark.parametrize("participant_index", range(0, MAX_DKG_SIZE, 2))
def test_finalize_handover(
    coordinator,
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
        coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    coordinator.grantRole(
        coordinator.HANDOVER_SUPERVISOR_ROLE(), handover_supervisor, sender=deployer
    )

    threshold, aggregated = activate_ritual(nodes, coordinator, ritualID)
    setup_node(incoming_node, coordinator, application, deployer)

    with ape.reverts("Not waiting for finalization"):
        coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    coordinator.handoverRequest(ritualID, departing_node, incoming_node, sender=handover_supervisor)

    with ape.reverts("Not waiting for finalization"):
        coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)
    decryption_request_static_key = os.urandom(42)
    coordinator.postHandoverTranscript(
        ritualID,
        departing_node,
        os.urandom(42),
        decryption_request_static_key,
        sender=incoming_node,
    )

    with ape.reverts("Not waiting for finalization"):
        coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)

    coordinator.postBlindedShare(ritualID, blinded_share, sender=departing_node)
    assert (
        coordinator.getHandoverState(ritualID, departing_node)
        == HandoverState.HANDOVER_AWAITING_FINALIZATION
    )

    assert not application.stakingProviderReleased(departing_node)
    tx = coordinator.finalizeHandover(ritualID, departing_node, sender=handover_supervisor)
    assert coordinator.getHandoverState(ritualID, departing_node) == HandoverState.NON_INITIATED
    assert application.stakingProviderReleased(departing_node)

    events = [event for event in tx.events if event.event_name == "HandoverFinalized"]
    assert events == [
        coordinator.HandoverFinalized(
            ritualId=ritualID,
            departingParticipant=departing_node,
            incomingParticipant=incoming_node,
        )
    ]

    handover_key = coordinator.getHandoverKey(ritualID, departing_node)
    handover = coordinator.handovers(handover_key)
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


def test_reorder_participants(
    coordinator,
    nodes,
    initiator,
    erc20,
    fee_model,
    deployer,
    global_allow_list,
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
    pairs = [[0, 3], [1, 2], [5, 10]]

    activate_ritual(nodes, coordinator, ritualID)

    # Get old participants with getParticipants() for later comparison
    old_participants = coordinator.getParticipants(ritualID)

    # Get individual participants via getParticipantFromProvider()
    participant_0 = coordinator.getParticipantFromProvider(ritualID, nodes[0])
    participant_1 = coordinator.getParticipantFromProvider(ritualID, nodes[1])
    participant_2 = coordinator.getParticipantFromProvider(ritualID, nodes[2])
    participant_3 = coordinator.getParticipantFromProvider(ritualID, nodes[3])
    participant_5 = coordinator.getParticipantFromProvider(ritualID, nodes[5])
    participant_10 = coordinator.getParticipantFromProvider(ritualID, nodes[10])

    with ape.reverts():
        coordinator.reorderParticipants(ritualID, pairs, sender=nodes[0])

    coordinator.reorderParticipants(ritualID, pairs, sender=deployer)

    # Check participants have been reordered
    participants = coordinator.getParticipants(ritualID)
    assert participants[0] == participant_3 
    assert participants[3] == participant_0
    assert participants[2] == participant_1
    assert participants[1] == participant_2
    assert participants[5] == participant_10
    assert participants[10] == participant_5

    assert participants[0] == old_participants[3]
    assert participants[3] == old_participants[0]
    assert participants[2] == old_participants[1]
    assert participants[1] == old_participants[2]
    assert participants[5] == old_participants[10]
    assert participants[10] == old_participants[5]

    # Check participants pagination still works
    max_page = 6
    participants_page_1 = coordinator.getParticipants(ritualID, 0, max_page, True)
    participants_page_2 = coordinator.getParticipants(ritualID, max_page, max_page, True)
    
    assert participants_page_1[0] == old_participants[3]
    assert participants_page_1[3] == old_participants[0]
    assert participants_page_1[2] == old_participants[1]
    assert participants_page_1[1] == old_participants[2]
    assert participants_page_1[5] == old_participants[10]

    assert participants_page_2[10 - max_page] == old_participants[5]
