import os
from enum import IntEnum

import pytest

# This file is pretty much the same as tests/test_coordinator.py, but with
# some of the tests removed and some of the tests modified to perform gas reporting.

TRANSCRIPT_SIZE = 500
TIMEOUT = 1000
MAX_DKG_SIZE = 64
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


# Need to use parameters here to restart the contract between tests
@pytest.mark.parametrize("n_nodes", [2, 4, 8, 16, 32, 64])
def test_initiate_ritual(coordinator, nodes, initiator, erc20, flat_rate_fee_model, n_nodes):
    selected_nodes = nodes[:n_nodes]
    with open("initiate_ritual.md", "a") as f:
        cost = flat_rate_fee_model.getRitualInitiationCost(selected_nodes, DURATION)
        erc20.approve(coordinator.address, cost, sender=initiator)
        tx_cost = coordinator.initiateRitual.estimate_gas_cost(
            selected_nodes, initiator, DURATION, sender=initiator
        )
        s = f"| {n_nodes} | {tx_cost} |\n"
        f.write(s)


def test_post_transcript(coordinator, nodes, initiator, erc20, flat_rate_fee_model):
    cost = flat_rate_fee_model.getRitualInitiationCost(nodes, DURATION)
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(nodes, initiator, DURATION, sender=initiator)

    # Not using parameters here for convenience of creating a markdown table
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
            f.write(s)


def test_post_aggregation(coordinator, nodes, initiator, erc20, flat_rate_fee_model):
    cost = flat_rate_fee_model.getRitualInitiationCost(nodes, DURATION)
    erc20.approve(coordinator.address, cost, sender=initiator)
    coordinator.initiateRitual(nodes, initiator, DURATION, sender=initiator)
    transcript = os.urandom(TRANSCRIPT_SIZE)
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    # Size of the aggregate is same as size of the transcript
    decryptionRequestStaticKeys = [os.urandom(42) for _ in nodes]
    publicKey = (os.urandom(32), os.urandom(16))
    with open("post_aggregation.md", "a") as f:
        f.write("| Aggregate size (bytes) | Total Gas |\n")
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
            aggregated = os.urandom(n_bytes)

            # We just need one node to post the aggregation, so we'll use the first one
            tx_cost = coordinator.postAggregation.estimate_gas_cost(
                0, aggregated, publicKey, decryptionRequestStaticKeys[0], sender=nodes[0]
            )
            s = f"| {n_bytes} | {tx_cost} |\n"
            f.write(s)
