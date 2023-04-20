import brownie
import pytest
from enum import IntEnum

import os

TRANSCRIPT_SIZE = 4000
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

def test_commit_to_transcript(coordinator, nodes, web3):
    coordinator.initiateRitual(nodes)

    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.AWAITING_TRANSCRIPTS

        transcript = os.urandom(TRANSCRIPT_SIZE)
        digest = web3.keccak(transcript)
        tx = coordinator.commitToTranscript(0, i, digest, {'from': node})
        
        assert "TranscriptCommitted" in tx.events
        event = tx.events["TranscriptCommitted"]
        assert event["ritualId"] == 0
        assert event["node"] == node
        assert event["transcriptDigest"] == digest.hex()

    assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS

def test_commit_to_transcript_but_not_part_of_ritual(coordinator, nodes, web3):
    coordinator.initiateRitual(nodes)
    with brownie.reverts("Node not part of ritual"):
        transcript = os.urandom(TRANSCRIPT_SIZE)
        digest = web3.keccak(transcript)
        coordinator.commitToTranscript(0, 5, digest, {'from': nodes[0]})

def test_commit_to_transcript_twice(coordinator, nodes, web3):
    transcript = os.urandom(TRANSCRIPT_SIZE)
    digest = web3.keccak(transcript)
    coordinator.initiateRitual(nodes)
    coordinator.commitToTranscript(0, 0, digest, {'from': nodes[0]})
    with brownie.reverts("Node already posted transcript"):
        coordinator.commitToTranscript(0, 0, digest, {'from': nodes[0]})

def test_commit_to_transcript_but_not_waiting_for_transcripts(coordinator, nodes, web3):
    coordinator.initiateRitual(nodes)
    for i, node in enumerate(nodes):
        transcript = os.urandom(TRANSCRIPT_SIZE)
        digest = web3.keccak(transcript)
        coordinator.commitToTranscript(0, i, digest, {'from': node})

    with brownie.reverts("Not waiting for transcripts"):
        coordinator.commitToTranscript(0, 1, digest, {'from': nodes[1]})

def test_post_aggregation(coordinator, nodes, web3, initiator):
    coordinator.initiateRitual(nodes, {'from': initiator})
    
    for i, node in enumerate(nodes):
        transcript = os.urandom(TRANSCRIPT_SIZE)
        digest = web3.keccak(transcript)
        coordinator.commitToTranscript(0, i, digest, {'from': node})

    aggregated = os.urandom(TRANSCRIPT_SIZE)
    publicKey = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(0) == RitualState.AWAITING_AGGREGATIONS
        digest = web3.keccak(aggregated)
        tx = coordinator.commitToAggregation(0, i, digest, publicKey, {'from': node})

        assert "AggregationCommitted" in tx.events
        event = tx.events["AggregationCommitted"]
        assert event["ritualId"] == 0
        assert event["node"] == node.address
        assert event["aggregatedTranscriptDigest"] == digest.hex()

    assert coordinator.getRitualState(0) == RitualState.FINALIZED
    assert "EndRitual" in tx.events
    event = tx.events["EndRitual"]
    assert event["ritualId"] == 0
    assert event["initiator"] == initiator.address
    assert event["status"] == RitualState.FINALIZED
