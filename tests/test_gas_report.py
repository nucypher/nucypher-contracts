import os
from enum import IntEnum

import pytest

TIMEOUT = 1000
MAX_DKG_SIZE = 64

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


@pytest.fixture(scope="module")
def nodes(accounts):
    return sorted(accounts[:16], key=lambda x: x.address)


INITIATOR_INDEX = 79
DEPLOYER_INDEX = 78


@pytest.fixture(scope="module")
def initiator(accounts):
    return accounts[INITIATOR_INDEX]


@pytest.fixture(scope="module")
def stake_info(project, accounts, nodes):
    deployer = accounts[DEPLOYER_INDEX]
    contract = project.StakeInfo.deploy([deployer], sender=deployer)
    for n in nodes:
        contract.updateOperator(n, n, sender=deployer)
        contract.updateAmount(n, 42, sender=deployer)
    return contract


@pytest.fixture(scope="module")
def coordinator(project, accounts, stake_info):
    return project.Coordinator.deploy(
        stake_info.address, TIMEOUT, MAX_DKG_SIZE, sender=accounts[DEPLOYER_INDEX]
    )


def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.timeout() == TIMEOUT
    assert coordinator.numberOfRituals() == 0


def test_initiate_ritual(coordinator, nodes, initiator):
    with open("initiate_ritual.md", "a") as f:
        f.write("| Number of nodes | Total Gas |\n")
        for n_nodes in [2, 4, 6, 8, 16]:
            selected_nodes = sorted(nodes[:n_nodes], key=lambda n: n.address)
            tx_cost = coordinator.initiateRitual.estimate_gas_cost(selected_nodes, sender=initiator)
            s = f"| {n_nodes} | {tx_cost} |\n"
            print(s)
            f.write(s)


def test_post_transcript(coordinator, nodes, initiator):
    coordinator.initiateRitual(nodes, sender=initiator)

    with open("transcript.md", "a") as f:
        f.write("| Transcript size (bytes) | Total Gas |\n")
        f.write("| ------- | --- |\n")
        for n_bytes in [
            424,
            664,
            712,
            1144,
            1192,
            1240,
            1288,
            2104,
            2200,
            2296,
            2440,
            4024,
            4264,
            4456,
            4744,
            7864,
            8344,
            8776,
            9352,
        ]:
            transcript = os.urandom(n_bytes)
            tx_cost = coordinator.postTranscript.estimate_gas_cost(0, transcript, sender=nodes[0])
            s = f"| {n_bytes} | {tx_cost} |\n"
            print(s)
            f.write(s)
