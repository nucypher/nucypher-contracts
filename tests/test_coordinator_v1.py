import brownie
import pytest
from enum import IntEnum

import os

TIMEOUT = 1000
MAX_DKG_SIZE = 64

RitualState = IntEnum(
    'RitualState',
    ['NON_INITIATED', 'AWAITING_TRANSCRIPTS', 'AWAITING_AGGREGATIONS', 'TIMEOUT', 'INVALID', 'FINALIZED'],
    start=0
)

@pytest.fixture(scope="function", autouse=True)
def isolate(fn_isolation):
    # perform a chain rewind after completing each test, to ensure proper isolation
    # https://eth-brownie.readthedocs.io/en/v1.10.3/tests-pytest-intro.html#isolation-fixtures
    pass

@pytest.fixture(scope="module")
def nodes(accounts):
    return sorted(accounts[:8], key=lambda x : x.address)

@pytest.fixture(scope="module")
def initiator(accounts):
    return accounts[9]

@pytest.fixture(scope="module")
def coordinator(Coordinator, BLS12381, accounts):
    # FIXME: UndeployedLibrary error forces me to deploy the BLS12381 library
    accounts[0].deploy(BLS12381);
    return accounts[8].deploy(Coordinator, TIMEOUT, MAX_DKG_SIZE);

def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.timeout() == TIMEOUT
    assert coordinator.numberOfRituals() == 0

def test_initiate_ritual(coordinator, nodes, initiator):
    with brownie.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(nodes[:5]*20, {'from': initiator})

    with brownie.reverts("Nodes must be sorted"):
        coordinator.initiateRitual(nodes[1:] + [nodes[0]])

    tx = coordinator.initiateRitual(nodes, {'from': initiator})

    assert "StartRitual" in tx.events
    event = tx.events["StartRitual"]
    assert event["ritualId"] == 0
    assert event["initiator"] == initiator
    assert event["nodes"] == nodes

    assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

def test_post_transcript(coordinator, nodes, web3):
    coordinator.initiateRitual(nodes)

    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

        transcript = os.urandom(10)
        tx = coordinator.postTranscript(0, i, transcript, {'from': node})
        
        assert "TranscriptPosted" in tx.events
        event = tx.events["TranscriptPosted"]
        assert event["ritualId"] == 0
        assert event["node"] == node
        assert event["transcriptDigest"] == web3.keccak(transcript).hex()

    assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS

def test_post_transcript_but_not_part_of_ritual(coordinator, nodes):
    coordinator.initiateRitual(nodes)
    with brownie.reverts("Node not part of ritual"):
        coordinator.postTranscript(0, 5, os.urandom(10), {'from': nodes[0]})

def test_post_transcript_but_already_posted_transcript(coordinator, nodes):
    coordinator.initiateRitual(nodes)
    coordinator.postTranscript(0, 0, os.urandom(10), {'from': nodes[0]})
    with brownie.reverts("Node already posted transcript"):
        coordinator.postTranscript(0, 0, os.urandom(10), {'from': nodes[0]})

def test_post_transcript_but_not_waiting_for_transcripts(coordinator, nodes):
    coordinator.initiateRitual(nodes)
    for i, node in enumerate(nodes):
        transcript = os.urandom(10)
        coordinator.postTranscript(0, i, transcript, {'from': node})

    with brownie.reverts("Not waiting for transcripts"):
        coordinator.postTranscript(0, 1, os.urandom(10), {'from': nodes[1]})

def test_post_aggregation(coordinator, nodes, web3, initiator):
    coordinator.initiateRitual(nodes, {'from': initiator})
    transcript = os.urandom(10)
    for i, node in enumerate(nodes):
        coordinator.postTranscript(0, i, transcript, {'from': node})

    aggregated = os.urandom(10)
    publicKey = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS
        tx = coordinator.postAggregation(0, i, aggregated, publicKey, {'from': node})

        assert "AggregationPosted" in tx.events
        event = tx.events["AggregationPosted"]
        assert event["ritualId"] == 0
        assert event["node"] == node.address
        assert event["aggregatedTranscriptDigest"] == web3.keccak(aggregated).hex()

    assert coordinator.getRitualState(0) == RitualState.FINALIZED
    assert "EndRitual" in tx.events
    event = tx.events["EndRitual"]
    assert event["ritualId"] == 0
    assert event["initiator"] == initiator.address
    assert event["status"] == RitualState.FINALIZED
