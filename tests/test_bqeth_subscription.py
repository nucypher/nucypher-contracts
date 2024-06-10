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
import os
from enum import IntEnum

import ape
import pytest
from eth_account.messages import encode_defunct
from web3 import Web3

FEE_RATE = 42
MAX_NODES = 10


ERC20_SUPPLY = 10**24
DURATION = 48 * 60 * 60
ONE_DAY = 24 * 60 * 60

MAX_DURATION = 3 * DURATION
YELLOW_PERIOD = ONE_DAY
RED_PERIOD = 5 * ONE_DAY

FEE = FEE_RATE * MAX_DURATION * MAX_NODES

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


@pytest.fixture(scope="module")
def treasury(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def adopter(accounts):
    return accounts[2]


@pytest.fixture()
def erc20(project, adopter):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=adopter)
    return token


@pytest.fixture()
def coordinator(project, creator):
    contract = project.CoordinatorForBqETHSubscriptionMock.deploy(
        sender=creator,
    )
    return contract


@pytest.fixture()
def subscription(project, creator, coordinator, erc20, treasury, adopter):
    contract = project.BqETHSubscription.deploy(
        coordinator.address,
        erc20.address,
        treasury,
        adopter,
        FEE_RATE,
        MAX_NODES,
        MAX_DURATION,
        YELLOW_PERIOD,
        RED_PERIOD,
        sender=creator,
    )
    coordinator.setFeeModel(contract.address, sender=creator)
    return contract


@pytest.fixture()
def global_allow_list(project, creator, coordinator, subscription, treasury):
    contract = project.GlobalAllowList.deploy(
        coordinator.address, subscription.address, sender=creator
    )
    subscription.initialize(contract.address, sender=treasury)
    return contract


def test_pay_subscription(erc20, subscription, adopter, chain):
    erc20.approve(subscription.address, 10 * FEE, sender=adopter)

    # First payment
    balance_before = erc20.balanceOf(adopter)
    assert subscription.packageFees() == FEE

    tx = subscription.payForSubscription(sender=adopter)
    timestamp = chain.pending_timestamp - 1
    assert subscription.getEndOfSubscription() == timestamp + MAX_DURATION
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + FEE == balance_before
    assert erc20.balanceOf(subscription.address) == FEE

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter, amount=FEE, endOfSubscription=timestamp + MAX_DURATION
        )
    ]

    # Top up
    balance_before = erc20.balanceOf(adopter)
    tx = subscription.payForSubscription(sender=adopter)
    assert subscription.getEndOfSubscription() == timestamp + 2 * MAX_DURATION
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + FEE == balance_before
    assert erc20.balanceOf(subscription.address) == 2 * FEE

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter, amount=FEE, endOfSubscription=timestamp + 2 * MAX_DURATION
        )
    ]


def test_withdraw(erc20, subscription, adopter, treasury):
    erc20.approve(subscription.address, 10 * FEE, sender=adopter)

    with ape.reverts("Only the beneficiary can call this method"):
        subscription.withdrawToBeneficiary(1, sender=adopter)

    with ape.reverts("Insufficient balance available"):
        subscription.withdrawToBeneficiary(1, sender=treasury)

    subscription.payForSubscription(sender=adopter)

    with ape.reverts("Insufficient balance available"):
        subscription.withdrawToBeneficiary(FEE + 1, sender=treasury)

    tx = subscription.withdrawToBeneficiary(FEE, sender=treasury)
    assert erc20.balanceOf(treasury) == FEE
    assert erc20.balanceOf(subscription.address) == 0

    events = subscription.WithdrawalToBeneficiary.from_receipt(tx)
    assert events == [subscription.WithdrawalToBeneficiary(beneficiary=treasury, amount=FEE)]


def test_process_ritual_payment(
    erc20, subscription, coordinator, global_allow_list, adopter, treasury
):
    ritual_id = 7
    number_of_providers = 6

    with ape.reverts("Only the Coordinator can call this method"):
        subscription.processRitualPayment(
            adopter, ritual_id, number_of_providers, DURATION, sender=treasury
        )
    with ape.reverts("Only adopter can initiate ritual"):
        coordinator.processRitualPayment(
            treasury, ritual_id, number_of_providers, DURATION, sender=treasury
        )
    with ape.reverts("Subscription has to be paid first"):
        coordinator.processRitualPayment(
            adopter, ritual_id, number_of_providers, DURATION, sender=treasury
        )

    erc20.approve(subscription.address, 10 * FEE, sender=adopter)
    subscription.payForSubscription(sender=adopter)

    with ape.reverts("Ritual parameters exceed available in package"):
        coordinator.processRitualPayment(
            adopter, ritual_id, MAX_NODES + 1, DURATION, sender=treasury
        )
    with ape.reverts("Ritual parameters exceed available in package"):
        coordinator.processRitualPayment(
            adopter,
            ritual_id,
            number_of_providers,
            MAX_DURATION + YELLOW_PERIOD + RED_PERIOD + 1,
            sender=treasury,
        )

    coordinator.setRitual(ritual_id, RitualState.NON_INITIATED, 0, treasury, sender=treasury)

    with ape.reverts("Access controller for ritual must be approved"):
        coordinator.processRitualPayment(
            adopter,
            ritual_id,
            MAX_NODES,
            MAX_DURATION + YELLOW_PERIOD + RED_PERIOD - 4,
            sender=treasury,
        )

    assert subscription.activeRitualId() == subscription.INACTIVE_RITUAL_ID()
    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_AWAITING_TRANSCRIPTS,
        0,
        global_allow_list.address,
        sender=treasury,
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, DURATION, sender=treasury
    )
    assert subscription.activeRitualId() == ritual_id

    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    with ape.reverts("Only failed rituals allowed to be reinitiated"):
        coordinator.processRitualPayment(
            adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
        )

    coordinator.setRitual(
        ritual_id, RitualState.DKG_INVALID, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
    )
    assert subscription.activeRitualId() == new_ritual_id

    ritual_id = new_ritual_id
    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.setRitual(
        ritual_id, RitualState.DKG_TIMEOUT, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
    )
    assert subscription.activeRitualId() == new_ritual_id

    ritual_id = new_ritual_id
    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.setRitual(
        ritual_id, RitualState.EXPIRED, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
    )
    assert subscription.activeRitualId() == new_ritual_id


def test_process_ritual_extending(
    erc20, subscription, coordinator, adopter, global_allow_list, treasury
):
    ritual_id = 6
    number_of_providers = 7

    with ape.reverts("Only the Coordinator can call this method"):
        subscription.processRitualExtending(
            adopter, ritual_id, number_of_providers, DURATION, sender=treasury
        )
    with ape.reverts("Ritual must be active"):
        coordinator.processRitualExtending(
            treasury, ritual_id, number_of_providers, DURATION, sender=treasury
        )

    erc20.approve(subscription.address, 10 * FEE, sender=adopter)
    subscription.payForSubscription(sender=adopter)
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, DURATION, sender=treasury
    )
    end_subscription = subscription.getEndOfSubscription()
    max_end_timestamp = end_subscription + YELLOW_PERIOD + RED_PERIOD

    new_ritual_id = ritual_id + 1
    with ape.reverts("Ritual must be active"):
        coordinator.processRitualExtending(
            treasury, new_ritual_id, number_of_providers, DURATION, sender=treasury
        )

    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_INVALID,
        max_end_timestamp + 1,
        global_allow_list.address,
        sender=treasury,
    )

    with ape.reverts("Ritual parameters exceed available in package"):
        coordinator.processRitualExtending(
            treasury, ritual_id, number_of_providers, DURATION, sender=treasury
        )

    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_INVALID,
        max_end_timestamp,
        global_allow_list.address,
        sender=treasury,
    )
    coordinator.processRitualExtending(
        adopter, ritual_id, number_of_providers, DURATION, sender=treasury
    )

    coordinator.setRitual(
        new_ritual_id,
        RitualState.DKG_INVALID,
        max_end_timestamp,
        global_allow_list.address,
        sender=treasury,
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
    )
    with ape.reverts("Ritual must be active"):
        coordinator.processRitualExtending(
            treasury, ritual_id, number_of_providers, DURATION, sender=treasury
        )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, DURATION, sender=treasury
    )


def test_before_set_authorization(
    erc20, subscription, coordinator, adopter, global_allow_list, treasury, creator, chain
):
    ritual_id = 6
    number_of_providers = 7

    assert subscription.address == global_allow_list.feeModel()

    with ape.reverts("Only Access Controller can call this method"):
        subscription.beforeSetAuthorization(0, [creator.address], True, sender=adopter)

    with ape.reverts("Ritual must be active"):
        global_allow_list.authorize(0, [creator.address], sender=adopter)

    erc20.approve(subscription.address, 10 * FEE, sender=adopter)
    subscription.payForSubscription(sender=adopter)
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, DURATION, sender=treasury
    )

    with ape.reverts("Ritual must be active"):
        global_allow_list.authorize(0, [creator.address], sender=adopter)
    global_allow_list.authorize(ritual_id, [creator.address], sender=adopter)

    end_subscription = subscription.getEndOfSubscription()
    chain.pending_timestamp = end_subscription + 1

    with ape.reverts("Subscription has expired"):
        global_allow_list.authorize(ritual_id, [creator.address], sender=adopter)

    subscription.payForSubscription(sender=adopter)
    global_allow_list.authorize(ritual_id, [creator.address], sender=adopter)


def test_before_is_authorized(
    erc20, subscription, coordinator, adopter, global_allow_list, treasury, creator, chain
):
    ritual_id = 6

    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=adopter.private_key)
    signature = signed_digest.signature

    assert subscription.address == global_allow_list.feeModel()

    with ape.reverts("Only Access Controller can call this method"):
        subscription.beforeIsAuthorized(0, sender=adopter)

    with ape.reverts("Ritual must be active"):
        global_allow_list.isAuthorized(0, bytes(signature), bytes(data))

    erc20.approve(subscription.address, 10 * FEE, sender=adopter)
    subscription.payForSubscription(sender=adopter)
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(adopter, ritual_id, MAX_NODES, DURATION, sender=treasury)
    global_allow_list.authorize(ritual_id, [adopter.address], sender=adopter)

    with ape.reverts("Ritual must be active"):
        global_allow_list.isAuthorized(0, bytes(signature), bytes(data))
    assert global_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    end_subscription = subscription.getEndOfSubscription()
    chain.pending_timestamp = end_subscription + YELLOW_PERIOD + 2

    with ape.reverts("Yellow period has expired"):
        global_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    subscription.payForSubscription(sender=adopter)
    assert global_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))
