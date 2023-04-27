import ape
import os
import pytest
from enum import IntEnum
from web3 import Web3



TIMEOUT = 1000
MAX_DKG_SIZE = 64

RitualState = IntEnum(
    'RitualState',
    ['NON_INITIATED', 'AWAITING_TRANSCRIPTS', 'AWAITING_AGGREGATIONS', 'TIMEOUT', 'INVALID', 'FINALIZED'],
    start=0
)

@pytest.fixture(scope="module")
def nodes(accounts):
    return sorted(accounts[:8], key=lambda x : x.address)

@pytest.fixture(scope="module")
def initiator(accounts):
    return accounts[9]

@pytest.fixture(scope="module")
def stake_info(project, accounts, nodes):
    deployer = accounts[8]
    contract = project.StakeInfo.deploy([deployer], sender=deployer)
    for n in nodes:
        contract.updateOperator(n, n, sender=deployer)
        contract.updateAmount(n, 42, sender=deployer)
    return contract

@pytest.fixture(scope="module")
def coordinator(project, accounts, stake_info):
    return project.Coordinator.deploy(stake_info.address, TIMEOUT, MAX_DKG_SIZE, sender=accounts[8]);

def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.timeout() == TIMEOUT
    assert coordinator.numberOfRituals() == 0

def test_initiate_ritual(coordinator, nodes, initiator):
    with ape.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(nodes[:5]*20, sender=initiator)

    with ape.reverts("Providers must be sorted"):
        coordinator.initiateRitual(nodes[1:] + [nodes[0]], sender=initiator)

    tx = coordinator.initiateRitual(nodes, sender=initiator)

    events = list(coordinator.StartRitual.from_receipt(tx))
    assert len(events) == 1
    event = events[0]
    assert event["ritualId"] == 0
    assert event["initiator"] == initiator
    assert event["participants"] == tuple(n.address.lower() for n in nodes)

    assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

def test_post_transcript(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)

    for node in nodes:
        assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

        transcript = os.urandom(10)
        tx = coordinator.postTranscript(0, transcript, sender=node)
        
        events = list(coordinator.TranscriptPosted.from_receipt(tx))
        assert len(events) == 1
        event = events[0]
        assert event["ritualId"] == 0
        assert event["node"] == node
        assert event["transcriptDigest"] == Web3.keccak(transcript)

    assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS

def test_post_transcript_but_not_part_of_ritual(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)
    with ape.reverts("Participant not part of ritual"):
        coordinator.postTranscript(0, os.urandom(10), sender=initiator)

def test_post_transcript_but_already_posted_transcript(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)
    coordinator.postTranscript(0, os.urandom(10), sender=nodes[0])
    with ape.reverts("Node already posted transcript"):
        coordinator.postTranscript(0, os.urandom(10), sender=nodes[0])

def test_post_transcript_but_not_waiting_for_transcripts(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)
    for node in nodes:
        transcript = os.urandom(10)
        coordinator.postTranscript(0, transcript, sender=node)

    with ape.reverts("Not waiting for transcripts"):
        coordinator.postTranscript(0, os.urandom(10), sender=nodes[1])

def test_post_aggregation(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)
    transcript = os.urandom(10)
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    aggregated = os.urandom(10)
    publicKey = (os.urandom(32), os.urandom(16))
    for node in nodes:
        assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS
        tx = coordinator.postAggregation(0, aggregated, publicKey, sender=node)

        events = list(coordinator.AggregationPosted.from_receipt(tx))
        assert len(events) == 1
        event = events[0]
        assert event["ritualId"] == 0
        assert event["node"] == node.address
        assert event["aggregatedTranscriptDigest"] == Web3.keccak(aggregated)

    assert coordinator.getRitualState(0) == RitualState.FINALIZED
    events = list(coordinator.EndRitual.from_receipt(tx))
    assert len(events) == 1
    event = events[0]
    assert event["ritualId"] == 0
    assert event["initiator"] == initiator.address
    assert event["ritualIsSuccessful"]
