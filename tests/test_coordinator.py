import os
from enum import IntEnum

import ape
import pytest
from web3 import Web3

TIMEOUT = 1000
MAX_DKG_SIZE = 4
FEE_RATE = 42
ERC20_SUPPLY = 10**24
DURATION = 1234

RitualState = IntEnum(
    "RitualState",
    [
        "NON_INITIATED",
        "AWAITING_TRANSCRIPTS",
        "AWAITING_AGGREGATIONS",
        "TIMEOUT",
        "INVALID",
        "FINALIZED",
    ],
    start=0,
)


# This formula returns an approximated size
# To have a representative size, create transcripts with `nucypher-core`
def transcript_size(shares, threshold):
    return int(424 + 240 * (shares / 2) + 50 * (threshold))


def gen_public_key():
    return (os.urandom(32), os.urandom(32), os.urandom(32))


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


@pytest.fixture()
def stake_info(project, deployer, nodes):
    contract = project.StakeInfo.deploy([deployer], sender=deployer)
    for n in nodes:
        contract.updateOperator(n, n, sender=deployer)
        contract.updateAmount(n, 42, sender=deployer)
    return contract


@pytest.fixture()
def erc20(project, initiator):
    # Create an ERC20 token (using NuCypherToken because it's easier, but could be any ERC20)
    token = project.NuCypherToken.deploy(ERC20_SUPPLY, sender=initiator)
    return token


@pytest.fixture()
def flat_rate_fee_model(project, deployer, stake_info, erc20):
    contract = project.FlatRateFeeModel.deploy(
        erc20.address, FEE_RATE, stake_info.address, sender=deployer
    )
    return contract


@pytest.fixture()
def coordinator(project, deployer, stake_info, flat_rate_fee_model, initiator):
    admin = deployer
    contract = project.Coordinator.deploy(
        stake_info.address,
        TIMEOUT,
        MAX_DKG_SIZE,
        admin,
        flat_rate_fee_model.address,
        sender=deployer,
    )
    contract.grantRole(contract.INITIATOR_ROLE(), initiator, sender=admin)
    return contract


def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.timeout() == TIMEOUT
    assert coordinator.numberOfRituals() == 0


def test_invalid_initiate_ritual(coordinator, nodes, accounts, initiator):
    with ape.reverts("Sender can't initiate ritual"):
        sender = accounts[3]
        coordinator.initiateRitual(nodes, sender, DURATION, sender=sender)

    with ape.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(nodes[:5] * 20, initiator, DURATION, sender=initiator)

    with ape.reverts("Invalid ritual duration"):
        coordinator.initiateRitual(nodes, initiator, 0, sender=initiator)

    with ape.reverts("Provider has not set their public key"):
        coordinator.initiateRitual(nodes, initiator, DURATION, sender=initiator)

    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    with ape.reverts("Providers must be sorted"):
        coordinator.initiateRitual(nodes[1:] + [nodes[0]], initiator, DURATION, sender=initiator)

    with ape.reverts("ERC20: insufficient allowance"):
        # Sender didn't approve enough tokens
        coordinator.initiateRitual(nodes, initiator, DURATION, sender=initiator)


def initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes):
    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)
    cost = flat_rate_fee_model.getRitualInitiationCost(nodes, DURATION)
    erc20.approve(coordinator.address, cost, sender=initiator)
    tx = coordinator.initiateRitual(nodes, initiator, DURATION, sender=initiator)
    return initiator, tx


def test_initiate_ritual(coordinator, nodes, initiator, erc20, flat_rate_fee_model):
    authority, tx = initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)

    events = list(coordinator.StartRitual.from_receipt(tx))
    assert len(events) == 1
    event = events[0]
    assert event["ritualId"] == 0
    assert event["authority"] == authority
    assert event["participants"] == tuple(n.address.lower() for n in nodes)

    assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS


def test_provider_public_key(coordinator, nodes):
    selected_provider = nodes[0]
    public_key = gen_public_key()
    tx = coordinator.setProviderPublicKey(public_key, sender=selected_provider)
    ritual_id = coordinator.numberOfRituals()

    events = list(coordinator.ParticipantPublicKeySet.from_receipt(tx))
    assert len(events) == 1
    event = events[0]
    assert event["participant"] == selected_provider
    assert event["publicKey"] == public_key
    assert coordinator.getProviderPublicKey(selected_provider, ritual_id) == public_key


def test_post_transcript(coordinator, nodes, initiator, erc20, flat_rate_fee_model):
    initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))

    for node in nodes:
        assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

        tx = coordinator.postTranscript(0, transcript, sender=node)

        events = list(coordinator.TranscriptPosted.from_receipt(tx))
        assert len(events) == 1
        event = events[0]
        assert event["ritualId"] == 0
        assert event["node"] == node
        assert event["transcriptDigest"] == Web3.keccak(transcript)

    participants = coordinator.getParticipants(0)
    for participant in participants:
        assert not participant.aggregated
        assert not participant.decryptionRequestStaticKey

    assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS


def test_post_transcript_but_not_part_of_ritual(
    coordinator, nodes, initiator, erc20, flat_rate_fee_model
):
    initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    with ape.reverts("Participant not part of ritual"):
        coordinator.postTranscript(0, transcript, sender=initiator)


def test_post_transcript_but_already_posted_transcript(
    coordinator, nodes, initiator, erc20, flat_rate_fee_model
):
    initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    coordinator.postTranscript(0, transcript, sender=nodes[0])
    with ape.reverts("Node already posted transcript"):
        coordinator.postTranscript(0, transcript, sender=nodes[0])


def test_post_transcript_but_not_waiting_for_transcripts(
    coordinator, nodes, initiator, erc20, flat_rate_fee_model
):
    initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    with ape.reverts("Not waiting for transcripts"):
        coordinator.postTranscript(0, transcript, sender=nodes[1])


def test_post_aggregation(coordinator, nodes, initiator, erc20, flat_rate_fee_model):
    initiate_ritual(coordinator, erc20, flat_rate_fee_model, initiator, nodes)
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS
        tx = coordinator.postAggregation(
            0, aggregated, dkg_public_key, decryption_request_static_keys[i], sender=node
        )

        events = list(coordinator.AggregationPosted.from_receipt(tx))
        assert len(events) == 1
        event = events[0]
        assert event["ritualId"] == 0
        assert event["node"] == node.address
        assert event["aggregatedTranscriptDigest"] == Web3.keccak(aggregated)

    participants = coordinator.getParticipants(0)
    for i, participant in enumerate(participants):
        assert participant.aggregated
        assert participant.decryptionRequestStaticKey == decryption_request_static_keys[i]

    assert coordinator.getRitualState(0) == RitualState.FINALIZED
    events = list(coordinator.EndRitual.from_receipt(tx))
    assert len(events) == 1
    event = events[0]
    assert event["ritualId"] == 0
    assert event["successful"]
