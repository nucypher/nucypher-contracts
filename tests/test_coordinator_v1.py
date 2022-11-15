import brownie
import pytest
from brownie import chain

import os

TRANSCRIPTS_WINDOW = 100
CONFIRMATIONS_WINDOW = 200

@pytest.fixture(scope="session")
def nodes(accounts):
    return sorted(accounts[:8], key=lambda x : x.address)

@pytest.fixture(scope="session")
def coordinator(CoordinatorV1, accounts):
    return accounts[8].deploy(CoordinatorV1, TRANSCRIPTS_WINDOW, CONFIRMATIONS_WINDOW)

def test_initial_parameters(coordinator):
    assert coordinator.DKG_SIZE() == 8
    assert coordinator.numberOfRituals() == 0
    assert coordinator.transcriptsWindow() == TRANSCRIPTS_WINDOW
    assert coordinator.confirmationsWindow() == CONFIRMATIONS_WINDOW

def test_initiate_ritual(coordinator, nodes):
    with brownie.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(nodes[:4])

    with brownie.reverts("Nodes must be sorted"):
        coordinator.initiateRitual(nodes[1:] + [nodes[0]])

    tx = coordinator.initiateRitual(nodes)

    assert "NewRitual" in tx.events
    event = tx.events["NewRitual"]
    assert event["ritualID"] == 0
    assert event["nodes"] == nodes

def test_post_transcript(coordinator, nodes, web3):
    coordinator.initiateRitual(nodes)
    for i, node in enumerate(nodes):
        transcript = os.urandom(10)
        tx = coordinator.postTranscript(0, i, transcript, {'from': node})
        
        assert "TranscriptPosted" in tx.events
        event = tx.events["TranscriptPosted"]
        assert event["ritualID"] == 0
        assert event["node"] == node
        assert event["transcriptDigest"] == web3.keccak(transcript).hex()

def test_post_confirmation(coordinator, nodes):
    coordinator.initiateRitual(nodes)
    for i, node in enumerate(nodes):
        transcript = os.urandom(10)
        coordinator.postTranscript(0, i, transcript, {'from': node})

    chain.sleep(150)
    for i, node in enumerate(nodes):
        confirmed = [j for j in range(0, 8) if j!=i]
        tx = coordinator.postConfirmation(0, i, confirmed, {'from': node})

        assert "ConfirmationPosted" in tx.events
        event = tx.events["ConfirmationPosted"]
        assert event["ritualID"] == 0
        assert event["node"] == node.address
        assert event["confirmedNodes"] == [nodes[j] for j in confirmed]
