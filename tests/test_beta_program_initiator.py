"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from enum import IntEnum

import ape
import pytest

DAY_IN_SECONDS = 60 * 60 * 24

AUTHORITY_SLOT = 0
DURATION_SLOT = 1
SENDER_SLOT = 2
RITUAL_ID_SLOT = 3
PAYMENT_SLOT = 4
FEE_RATE = 42

RitualState = IntEnum(
    "RitualState",
    [
        "NON_INITIATED",
        "DKG_AWAITING_TRANSCRIPTS",
        "DKG_AWAITING_AGGREGATIONS",
        "DKG_TIMEOUT",
        "DKG_INVALID",
        "ACTIVE",
        "EXPIRED",
    ],
    start=0,
)


@pytest.fixture()
def executor(accounts):
    return accounts[1]


@pytest.fixture()
def token(project, creator):
    token = project.TestToken.deploy(0, sender=creator)
    return token


@pytest.fixture()
def coordinator(project, creator):
    contract = project.CoordinatorForBetaProgramInitiatorMock.deploy(sender=creator)
    return contract


@pytest.fixture()
def fee_model(project, creator, coordinator, token):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, token.address, FEE_RATE, sender=creator
    )
    return contract


@pytest.fixture()
def beta_program_initiator(project, coordinator, executor, creator, fee_model):
    contract = project.BetaProgramInitiator.deploy(
        coordinator.address, executor, fee_model.address, sender=creator
    )
    return contract


def test_register(accounts, beta_program_initiator, token, fee_model):
    (
        initiator_1,
        initiator_2,
        authority,
        node_1,
        node_2,
        *everyone_else,
    ) = accounts[2:]
    no_ritual = beta_program_initiator.NO_RITUAL()

    nodes = [node_1, node_2]
    duration = DAY_IN_SECONDS
    ritual_cost = fee_model.getRitualInitiationCost(len(nodes), duration)

    # Can't register request without token transfer approval
    with ape.reverts():
        beta_program_initiator.registerInitiationRequest(
            nodes, authority, duration, sender=initiator_1
        )

    # Register request
    token.mint(initiator_1, 10 * ritual_cost, sender=initiator_1)
    token.approve(beta_program_initiator.address, 10 * ritual_cost, sender=initiator_1)
    tx = beta_program_initiator.registerInitiationRequest(
        nodes, authority, duration, sender=initiator_1
    )
    assert beta_program_initiator.getRequestsLength() == 1
    assert beta_program_initiator.getProviders(0) == nodes
    request = beta_program_initiator.requests(0)
    assert request[AUTHORITY_SLOT] == authority
    assert request[DURATION_SLOT] == duration
    assert request[SENDER_SLOT] == initiator_1
    assert request[RITUAL_ID_SLOT] == no_ritual
    assert request[PAYMENT_SLOT] == ritual_cost
    assert token.balanceOf(beta_program_initiator) == ritual_cost

    events = beta_program_initiator.RequestRegistered.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.sender == initiator_1
    assert event.requestIndex == 0
    assert event.providers == [n.address for n in nodes]
    assert event.authority == authority
    assert event.duration == duration
    assert event.payment == ritual_cost

    # Register another request
    nodes = [node_1]
    duration = 3 * DAY_IN_SECONDS
    ritual_cost_2 = fee_model.getRitualInitiationCost(len(nodes), duration)

    token.mint(initiator_2, ritual_cost_2, sender=initiator_2)
    token.approve(beta_program_initiator.address, ritual_cost_2, sender=initiator_2)
    tx = beta_program_initiator.registerInitiationRequest(
        nodes, authority, duration, sender=initiator_2
    )
    assert beta_program_initiator.getRequestsLength() == 2
    assert beta_program_initiator.getProviders(1) == nodes
    request = beta_program_initiator.requests(1)
    assert request[AUTHORITY_SLOT] == authority
    assert request[DURATION_SLOT] == duration
    assert request[SENDER_SLOT] == initiator_2
    assert request[RITUAL_ID_SLOT] == no_ritual
    assert request[PAYMENT_SLOT] == ritual_cost_2
    assert token.balanceOf(beta_program_initiator) == ritual_cost + ritual_cost_2

    events = beta_program_initiator.RequestRegistered.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.sender == initiator_2
    assert event.requestIndex == 1
    assert event.providers == [n.address for n in nodes]
    assert event.authority == authority
    assert event.duration == duration
    assert event.payment == ritual_cost_2


def test_cancel(accounts, beta_program_initiator, token, executor, fee_model):
    (
        initiator_1,
        initiator_2,
        authority,
        node_1,
        node_2,
        *everyone_else,
    ) = accounts[2:]

    nodes = [node_1, node_2]
    duration = DAY_IN_SECONDS
    ritual_cost = fee_model.getRitualInitiationCost(len(nodes), duration)

    token.mint(initiator_1, 10 * ritual_cost, sender=initiator_1)
    token.approve(beta_program_initiator.address, 10 * ritual_cost, sender=initiator_1)
    token.mint(initiator_2, 10 * ritual_cost, sender=initiator_2)
    token.approve(beta_program_initiator.address, 10 * ritual_cost, sender=initiator_2)

    # Can't cancel non-existent request
    with ape.reverts("Non-existent request"):
        beta_program_initiator.cancelInitiationRequest(0, sender=executor)

    # Register three requests
    beta_program_initiator.registerInitiationRequest(nodes, authority, duration, sender=initiator_1)
    beta_program_initiator.registerInitiationRequest(nodes, authority, duration, sender=initiator_1)
    beta_program_initiator.registerInitiationRequest(nodes, authority, duration, sender=initiator_2)

    # Only initiator or executor can cancel request
    with ape.reverts("Not allowed to cancel"):
        beta_program_initiator.cancelInitiationRequest(0, sender=initiator_2)
    with ape.reverts("Not allowed to cancel"):
        beta_program_initiator.cancelInitiationRequest(2, sender=initiator_1)

    # Initiator cancels request
    balance_before = token.balanceOf(initiator_1)
    tx = beta_program_initiator.cancelInitiationRequest(0, sender=initiator_1)
    assert beta_program_initiator.requests(0)[PAYMENT_SLOT] == 0
    balance_after = token.balanceOf(initiator_1)
    assert balance_after - balance_before == ritual_cost

    events = beta_program_initiator.RequestCanceled.from_receipt(tx)
    assert events == [beta_program_initiator.RequestCanceled(initiator_1, 0)]

    # Executor cancels request
    balance_before = token.balanceOf(initiator_2)
    tx = beta_program_initiator.cancelInitiationRequest(2, sender=executor)
    assert beta_program_initiator.requests(2)[PAYMENT_SLOT] == 0
    balance_after = token.balanceOf(initiator_2)
    assert balance_after - balance_before == ritual_cost

    events = beta_program_initiator.RequestCanceled.from_receipt(tx)
    assert events == [beta_program_initiator.RequestCanceled(executor, 2)]

    # Can't cancel twice
    with ape.reverts("Request canceled"):
        beta_program_initiator.cancelInitiationRequest(0, sender=executor)
    with ape.reverts("Request canceled"):
        beta_program_initiator.cancelInitiationRequest(2, sender=initiator_2)

    # Can't cancel an executed request
    beta_program_initiator.executeInitiationRequest(1, sender=executor)
    with ape.reverts("Request already executed"):
        beta_program_initiator.cancelInitiationRequest(1, sender=executor)


def test_execute(accounts, beta_program_initiator, token, coordinator, executor, fee_model):
    (
        initiator_1,
        initiator_2,
        authority_1,
        authority_2,
        node_1,
        node_2,
        *everyone_else,
    ) = accounts[2:]
    no_ritual = beta_program_initiator.NO_RITUAL()

    nodes_1 = [node_1, node_2]
    duration_1 = DAY_IN_SECONDS
    ritual_cost_1 = fee_model.getRitualInitiationCost(len(nodes_1), duration_1)
    nodes_2 = [node_1]
    duration_2 = 2 * duration_1
    ritual_cost_2 = fee_model.getRitualInitiationCost(len(nodes_2), duration_2)

    token.mint(initiator_1, 10 * ritual_cost_1, sender=initiator_1)
    token.approve(beta_program_initiator.address, 10 * ritual_cost_1, sender=initiator_1)
    token.mint(initiator_2, 10 * ritual_cost_2, sender=initiator_2)
    token.approve(beta_program_initiator.address, 10 * ritual_cost_2, sender=initiator_2)

    # Can't execute non-existent request
    with ape.reverts("Non-existent request"):
        beta_program_initiator.executeInitiationRequest(0, sender=executor)

    # Register three requests
    beta_program_initiator.registerInitiationRequest(
        nodes_1, authority_1, duration_1, sender=initiator_1
    )
    beta_program_initiator.registerInitiationRequest(
        nodes_2, authority_2, duration_2, sender=initiator_2
    )
    beta_program_initiator.registerInitiationRequest(
        nodes_2, authority_1, duration_1, sender=initiator_1
    )

    # Only executor can execute request
    with ape.reverts("Only executor can call"):
        beta_program_initiator.executeInitiationRequest(0, sender=initiator_1)

    # Can't execute canceled request
    beta_program_initiator.cancelInitiationRequest(2, sender=initiator_1)
    with ape.reverts("Request canceled"):
        beta_program_initiator.executeInitiationRequest(2, sender=executor)

    # Execute request
    balance_before = token.balanceOf(beta_program_initiator.address)
    tx = beta_program_initiator.executeInitiationRequest(1, sender=executor)
    assert beta_program_initiator.requests(1)[RITUAL_ID_SLOT] == 0
    assert beta_program_initiator.requests(0)[RITUAL_ID_SLOT] == no_ritual
    balance_after = token.balanceOf(beta_program_initiator.address)
    assert balance_before - balance_after == ritual_cost_2
    assert token.balanceOf(fee_model.address) == ritual_cost_2

    assert coordinator.getRitualsLength() == 1
    assert coordinator.getProviders(0) == nodes_2
    ritual = coordinator.rituals(0)
    assert ritual[0] == beta_program_initiator.address
    assert ritual[1] == authority_2
    assert ritual[2] == duration_2
    assert ritual[3] == 1
    # assert ritual[4] == ritual_cost_2
    assert ritual[5] == fee_model.address

    events = beta_program_initiator.RequestExecuted.from_receipt(tx)
    assert events == [beta_program_initiator.RequestExecuted(1, 0)]

    # Can't execute twice
    with ape.reverts("Request already executed"):
        beta_program_initiator.executeInitiationRequest(1, sender=executor)

    # Can't execute request if ritual cost changes
    # fee_rate = fee_model.feeRatePerSecond()
    # coordinator.setFeeRatePerSecond(2 * fee_rate, sender=executor)
    # with ape.reverts("Ritual initiation cost has changed"):
    #     beta_program_initiator.executeInitiationRequest(0, sender=executor)
    # coordinator.setFeeRatePerSecond(fee_rate // 2, sender=executor)
    # with ape.reverts("Ritual initiation cost has changed"):
    #     beta_program_initiator.executeInitiationRequest(0, sender=executor)

    # Return fee rate back and execute request again
    # coordinator.setFeeRatePerSecond(fee_rate, sender=executor)
    balance_before = token.balanceOf(beta_program_initiator.address)
    tx = beta_program_initiator.executeInitiationRequest(0, sender=executor)
    assert beta_program_initiator.requests(0)[RITUAL_ID_SLOT] == 1
    assert beta_program_initiator.requests(1)[RITUAL_ID_SLOT] == 0
    balance_after = token.balanceOf(beta_program_initiator.address)
    assert balance_before - balance_after == ritual_cost_1
    assert token.balanceOf(fee_model.address) == ritual_cost_2 + ritual_cost_1

    assert coordinator.getRitualsLength() == 2
    assert coordinator.getProviders(1) == nodes_1
    ritual = coordinator.rituals(1)
    assert ritual[0] == beta_program_initiator.address
    assert ritual[1] == authority_1
    assert ritual[2] == duration_1
    assert ritual[3] == 1
    # assert ritual[4] == ritual_cost_1
    assert ritual[5] == fee_model.address

    events = beta_program_initiator.RequestExecuted.from_receipt(tx)
    assert events == [beta_program_initiator.RequestExecuted(0, 1)]


def test_refund(accounts, beta_program_initiator, token, coordinator, executor, fee_model):
    (
        initiator_1,
        initiator_2,
        authority,
        node_1,
        node_2,
        *everyone_else,
    ) = accounts[2:]

    nodes = [node_1, node_2]
    duration_1 = DAY_IN_SECONDS
    ritual_cost_1 = fee_model.getRitualInitiationCost(len(nodes), duration_1)
    duration_2 = 3 * duration_1
    ritual_cost_2 = fee_model.getRitualInitiationCost(len(nodes), duration_2)

    token.mint(initiator_1, 10 * ritual_cost_1, sender=initiator_1)
    token.approve(beta_program_initiator.address, 10 * ritual_cost_1, sender=initiator_1)
    token.mint(initiator_2, 10 * ritual_cost_2, sender=initiator_2)
    token.approve(beta_program_initiator.address, 10 * ritual_cost_2, sender=initiator_2)

    # Can't refund non-existent request
    with ape.reverts("Non-existent request"):
        beta_program_initiator.refundFailedRequest(0, sender=executor)

    # Register three requests
    beta_program_initiator.registerInitiationRequest(
        nodes, authority, duration_1, sender=initiator_1
    )
    beta_program_initiator.registerInitiationRequest(
        nodes, authority, duration_2, sender=initiator_2
    )
    beta_program_initiator.registerInitiationRequest(
        nodes, authority, duration_2, sender=initiator_1
    )

    # Can't refund not executed request
    with ape.reverts("Request is not executed"):
        beta_program_initiator.refundFailedRequest(0, sender=executor)
    beta_program_initiator.cancelInitiationRequest(2, sender=initiator_1)
    with ape.reverts("Request is not executed"):
        beta_program_initiator.refundFailedRequest(2, sender=initiator_2)

    # Can't refund not failed request
    beta_program_initiator.executeInitiationRequest(1, sender=executor)
    beta_program_initiator.executeInitiationRequest(0, sender=executor)
    request_0_ritual_id = 1
    request_1_ritual_id = 0
    for state in [
        RitualState.NON_INITIATED,
        RitualState.DKG_AWAITING_TRANSCRIPTS,
        RitualState.DKG_AWAITING_AGGREGATIONS,
        RitualState.ACTIVE,
        RitualState.EXPIRED,
    ]:
        coordinator.setRitualState(request_0_ritual_id, state, sender=initiator_2)
        with ape.reverts("Ritual is not failed"):
            beta_program_initiator.refundFailedRequest(request_0_ritual_id, sender=initiator_2)

    # Refund failed request
    coordinator.setRitualState(request_0_ritual_id, RitualState.DKG_TIMEOUT, sender=initiator_2)

    assert token.balanceOf(beta_program_initiator.address) == 0
    initiator_1_balance_before = token.balanceOf(initiator_1)
    fee_model_balance_before = token.balanceOf(fee_model.address)
    assert fee_model_balance_before == ritual_cost_1 + ritual_cost_2
    pending_fees_1_before = fee_model.pendingFees(request_0_ritual_id)
    assert pending_fees_1_before == ritual_cost_1

    tx = beta_program_initiator.refundFailedRequest(0, sender=initiator_2)

    fee_model_balance_after = token.balanceOf(fee_model.address)
    fee_deduction_1 = fee_model.feeDeduction(pending_fees_1_before, duration_1)
    pending_fees_1_after = fee_model.pendingFees(request_0_ritual_id)
    assert fee_model_balance_after == ritual_cost_2 + fee_deduction_1
    assert pending_fees_1_after == 0
    assert token.balanceOf(beta_program_initiator.address) == 0

    refund_1 = ritual_cost_1 - fee_deduction_1
    initiator_1_balance_after = token.balanceOf(initiator_1)
    assert initiator_1_balance_after - initiator_1_balance_before == refund_1
    assert beta_program_initiator.requests(0)[RITUAL_ID_SLOT] == request_0_ritual_id
    assert beta_program_initiator.requests(0)[PAYMENT_SLOT] == 0

    events = beta_program_initiator.FailedRequestRefunded.from_receipt(tx)
    assert events == [beta_program_initiator.FailedRequestRefunded(0, refund_1)]

    # Can't refund again
    with ape.reverts("Refund already processed"):
        beta_program_initiator.refundFailedRequest(0, sender=executor)

    # Refund failed request without pending fees
    coordinator.setRitualState(request_1_ritual_id, RitualState.DKG_INVALID, sender=initiator_2)

    assert token.balanceOf(beta_program_initiator.address) == 0
    initiator_2_balance_before = token.balanceOf(initiator_2)
    fee_model_balance_before = token.balanceOf(fee_model.address)
    assert fee_model_balance_before == ritual_cost_2 + fee_deduction_1
    pending_fees_2_before = fee_model.pendingFees(request_1_ritual_id)
    assert pending_fees_2_before == ritual_cost_2

    fee_model.processPendingFee(request_1_ritual_id, sender=initiator_1)
    assert fee_model.pendingFees(request_1_ritual_id) == 0

    fee_deduction_2 = fee_model.feeDeduction(pending_fees_2_before, duration_2)
    refund_2 = ritual_cost_2 - fee_deduction_2
    assert token.balanceOf(beta_program_initiator.address) == refund_2

    tx = beta_program_initiator.refundFailedRequest(1, sender=initiator_2)

    assert token.balanceOf(beta_program_initiator.address) == 0
    initiator_2_balance_after = token.balanceOf(initiator_2)
    assert initiator_2_balance_after - initiator_2_balance_before == refund_2
    assert beta_program_initiator.requests(1)[RITUAL_ID_SLOT] == request_1_ritual_id
    assert beta_program_initiator.requests(1)[PAYMENT_SLOT] == 0

    events = beta_program_initiator.FailedRequestRefunded.from_receipt(tx)
    assert events == [beta_program_initiator.FailedRequestRefunded(1, refund_2)]
