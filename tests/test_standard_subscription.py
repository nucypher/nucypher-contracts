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
from ape.utils import ZERO_ADDRESS
from eth_account.messages import encode_defunct
from web3 import Web3

BASE_FEE_RATE = 42
BASE_FEE_RATE_INCREASE = 10  # 10%
MAX_NODES = 10
ENCRYPTORS_FEE_RATE = 77


ERC20_SUPPLY = 10**24
ONE_DAY = 24 * 60 * 60
DURATION = 10 * ONE_DAY

PACKAGE_DURATION = 3 * DURATION
YELLOW_PERIOD = ONE_DAY
RED_PERIOD = 5 * ONE_DAY


def base_fee(period_number):
    return (
        BASE_FEE_RATE
        * pow(100 + BASE_FEE_RATE_INCREASE, period_number)
        * PACKAGE_DURATION
        * MAX_NODES
        // pow(100, period_number)
    )


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


@pytest.fixture(scope="module")
def adopter_setter(accounts):
    return accounts[3]


@pytest.fixture()
def erc20(project, adopter):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=adopter)
    return token


@pytest.fixture()
def coordinator(project, creator):
    contract = project.CoordinatorForStandardSubscriptionMock.deploy(
        sender=creator,
    )
    return contract


@pytest.fixture()
def global_allow_list(project, creator, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=creator)
    return contract


@pytest.fixture()
def subscription(
    project, creator, coordinator, global_allow_list, erc20, adopter_setter, treasury, oz_dependency
):
    contract = project.StandardSubscription.deploy(
        coordinator.address,
        global_allow_list.address,
        erc20.address,
        adopter_setter,
        BASE_FEE_RATE,
        BASE_FEE_RATE_INCREASE * 100,
        ENCRYPTORS_FEE_RATE,
        MAX_NODES,
        PACKAGE_DURATION,
        YELLOW_PERIOD,
        RED_PERIOD,
        sender=creator,
    )

    encoded_initializer_function = b""
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        creator,
        encoded_initializer_function,
        sender=creator,
    )
    proxy_contract = project.StandardSubscription.at(proxy.address)
    coordinator.setFeeModel(proxy_contract.address, sender=creator)
    proxy_contract.initialize(treasury.address, sender=treasury)
    return proxy_contract


def test_adopter_setter(subscription, adopter_setter, adopter):
    with ape.reverts("Only adopter setter can set adopter"):
        subscription.setAdopter(adopter, sender=adopter)
    with ape.reverts("Adopter can be set only once with not zero address"):
        subscription.setAdopter(ZERO_ADDRESS, sender=adopter_setter)
    subscription.setAdopter(adopter, sender=adopter_setter)
    assert subscription.adopter() == adopter
    with ape.reverts("Adopter can be set only once with not zero address"):
        subscription.setAdopter(adopter_setter, sender=adopter_setter)


def test_pay_subscription(
    erc20, subscription, coordinator, global_allow_list, adopter, adopter_setter, treasury, chain
):
    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)

    # First payment
    balance_before = erc20.balanceOf(adopter)
    current_base_fee = base_fee(0)
    assert subscription.baseFees() == current_base_fee
    assert subscription.baseFees(0) == current_base_fee
    assert subscription.baseFees(1) == base_fee(1)
    assert subscription.baseFees(2) == base_fee(2)
    assert subscription.baseFees(3) == base_fee(3)
    assert subscription.startOfSubscription() == 0
    assert subscription.getEndOfSubscription() == 0
    assert subscription.getCurrentPeriodNumber() == 0
    assert subscription.billingInfo(0) == (False, 0)

    tx = subscription.payForSubscription(0, sender=adopter)
    end_subscription = 0
    assert subscription.startOfSubscription() == 0
    assert subscription.getEndOfSubscription() == 0
    assert subscription.getCurrentPeriodNumber() == 0
    assert subscription.billingInfo(0) == (True, 0)
    assert subscription.billingInfo(1) == (False, 0)
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + current_base_fee == balance_before
    assert erc20.balanceOf(subscription.address) == current_base_fee

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            amount=current_base_fee,
            encryptorSlots=0,
            endOfSubscription=end_subscription,
        )
    ]

    # Top up
    encryptor_slots = 10
    encryptor_fees = ENCRYPTORS_FEE_RATE * PACKAGE_DURATION * encryptor_slots
    balance_before = erc20.balanceOf(adopter)
    subscription_balance_before = erc20.balanceOf(subscription.address)
    tx = subscription.payForSubscription(encryptor_slots, sender=adopter)
    end_subscription = 0
    assert subscription.getEndOfSubscription() == end_subscription
    balance_after = erc20.balanceOf(adopter)
    current_base_fee = base_fee(1)
    assert balance_after + current_base_fee + encryptor_fees == balance_before
    assert (
        erc20.balanceOf(subscription.address)
        == subscription_balance_before + current_base_fee + encryptor_fees
    )
    assert subscription.getCurrentPeriodNumber() == 0
    assert subscription.billingInfo(0) == (True, 0)
    assert subscription.billingInfo(1) == (True, encryptor_slots)

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            amount=current_base_fee + encryptor_fees,
            encryptorSlots=encryptor_slots,
            endOfSubscription=end_subscription,
        )
    ]

    # Can't pay in advance more than one time cycle
    with ape.reverts("Next billing period already paid"):
        subscription.payForSubscription(0, sender=adopter)

    ritual_id = 1
    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_AWAITING_TRANSCRIPTS,
        0,
        global_allow_list.address,
        sender=treasury,
    )
    coordinator.processRitualPayment(adopter, ritual_id, MAX_NODES, DURATION, sender=treasury)
    timestamp = chain.pending_timestamp - 1
    end_subscription = timestamp + 2 * PACKAGE_DURATION
    assert subscription.startOfSubscription() == timestamp
    assert subscription.getEndOfSubscription() == end_subscription

    chain.pending_timestamp = timestamp + PACKAGE_DURATION + 1
    assert subscription.baseFees() == current_base_fee

    # Top up
    balance_before = erc20.balanceOf(adopter)
    subscription_balance_before = erc20.balanceOf(subscription.address)
    tx = subscription.payForSubscription(encryptor_slots, sender=adopter)
    end_subscription = timestamp + 3 * PACKAGE_DURATION
    assert subscription.startOfSubscription() == timestamp
    assert subscription.getEndOfSubscription() == end_subscription
    balance_after = erc20.balanceOf(adopter)
    current_base_fee = base_fee(2)
    assert balance_after + current_base_fee + encryptor_fees == balance_before
    assert (
        erc20.balanceOf(subscription.address)
        == subscription_balance_before + current_base_fee + encryptor_fees
    )
    assert subscription.getCurrentPeriodNumber() == 1
    assert subscription.billingInfo(0) == (True, 0)
    assert subscription.billingInfo(1) == (True, encryptor_slots)
    assert subscription.billingInfo(2) == (True, encryptor_slots)

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            amount=current_base_fee + encryptor_fees,
            encryptorSlots=encryptor_slots,
            endOfSubscription=end_subscription,
        )
    ]

    # Can't pay after red period is over
    chain.pending_timestamp = end_subscription + YELLOW_PERIOD + RED_PERIOD + 1
    assert subscription.getCurrentPeriodNumber() == 3
    with ape.reverts("Subscription is over"):
        subscription.payForSubscription(0, sender=adopter)


def test_pay_encryptor_slots(
    erc20, subscription, coordinator, global_allow_list, adopter, adopter_setter, treasury, chain
):
    encryptor_slots = 10
    assert (
        subscription.encryptorFees(encryptor_slots, PACKAGE_DURATION)
        == encryptor_slots * PACKAGE_DURATION * ENCRYPTORS_FEE_RATE
    )

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)

    with ape.reverts("Current billing period must be paid"):
        subscription.payForEncryptorSlots(encryptor_slots, sender=adopter)

    subscription.payForSubscription(encryptor_slots, sender=adopter)
    subscription.payForSubscription(0, sender=adopter)
    assert subscription.billingInfo(0) == (True, encryptor_slots)
    assert subscription.billingInfo(1) == (True, 0)

    duration = PACKAGE_DURATION // 3
    chain.pending_timestamp += duration
    encryptor_fees = encryptor_slots * PACKAGE_DURATION * ENCRYPTORS_FEE_RATE
    assert subscription.encryptorFees(encryptor_slots, PACKAGE_DURATION) == encryptor_fees

    adopter_balance_before = erc20.balanceOf(adopter)
    subscription_balance_before = erc20.balanceOf(subscription.address)
    tx = subscription.payForEncryptorSlots(encryptor_slots, sender=adopter)
    adopter_balance_after = erc20.balanceOf(adopter)
    subscription_balance_after = erc20.balanceOf(subscription.address)
    assert adopter_balance_after + encryptor_fees == adopter_balance_before
    assert subscription_balance_before + encryptor_fees == subscription_balance_after
    assert subscription.billingInfo(0) == (True, 2 * encryptor_slots)
    assert subscription.billingInfo(1) == (True, 0)

    events = subscription.EncryptorSlotsPaid.from_receipt(tx)
    assert events == [
        subscription.EncryptorSlotsPaid(
            sponsor=adopter,
            amount=encryptor_fees,
            encryptorSlots=encryptor_slots,
            endOfCurrentPeriod=0,
        )
    ]

    ritual_id = 1
    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_AWAITING_TRANSCRIPTS,
        0,
        global_allow_list.address,
        sender=treasury,
    )
    coordinator.processRitualPayment(adopter, ritual_id, MAX_NODES, DURATION, sender=treasury)
    timestamp = chain.pending_timestamp - 1

    duration = PACKAGE_DURATION // 5
    chain.pending_timestamp = timestamp + PACKAGE_DURATION + duration
    encryptor_fees = encryptor_slots * (PACKAGE_DURATION - duration) * ENCRYPTORS_FEE_RATE

    adopter_balance_before = erc20.balanceOf(adopter)
    subscription_balance_before = erc20.balanceOf(subscription.address)
    tx = subscription.payForEncryptorSlots(encryptor_slots, sender=adopter)
    adopter_balance_after = erc20.balanceOf(adopter)
    subscription_balance_after = erc20.balanceOf(subscription.address)
    assert adopter_balance_after + encryptor_fees == adopter_balance_before
    assert subscription_balance_before + encryptor_fees == subscription_balance_after
    assert subscription.billingInfo(0) == (True, 2 * encryptor_slots)
    assert subscription.billingInfo(1) == (True, encryptor_slots)

    events = subscription.EncryptorSlotsPaid.from_receipt(tx)
    assert events == [
        subscription.EncryptorSlotsPaid(
            sponsor=adopter,
            amount=encryptor_fees,
            encryptorSlots=encryptor_slots,
            endOfCurrentPeriod=timestamp + 2 * PACKAGE_DURATION,
        )
    ]

    chain.pending_timestamp = timestamp + 2 * PACKAGE_DURATION + duration
    with ape.reverts("Current billing period must be paid"):
        subscription.payForEncryptorSlots(encryptor_slots, sender=adopter)


def test_withdraw(erc20, subscription, adopter, adopter_setter, treasury, global_allow_list):
    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)

    with ape.reverts("Insufficient balance available"):
        subscription.withdrawToTreasury(sender=adopter)

    subscription.payForSubscription(0, sender=adopter)

    current_base_fee = base_fee(0)
    tx = subscription.withdrawToTreasury(sender=adopter)
    assert erc20.balanceOf(treasury) == current_base_fee
    assert erc20.balanceOf(subscription.address) == 0

    events = subscription.WithdrawalToTreasury.from_receipt(tx)
    assert events == [subscription.WithdrawalToTreasury(treasury=treasury, amount=current_base_fee)]


def test_process_ritual_payment(
    erc20, subscription, coordinator, global_allow_list, adopter, adopter_setter, treasury
):
    ritual_id = 7
    number_of_providers = 6
    subscription.setAdopter(adopter, sender=adopter_setter)

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

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.payForSubscription(0, sender=adopter)

    with ape.reverts("Ritual parameters exceed available in package"):
        coordinator.processRitualPayment(
            adopter, ritual_id, MAX_NODES + 1, DURATION, sender=treasury
        )
    with ape.reverts("Ritual parameters exceed available in package"):
        coordinator.processRitualPayment(
            adopter,
            ritual_id,
            number_of_providers,
            PACKAGE_DURATION + YELLOW_PERIOD + RED_PERIOD + 1,
            sender=treasury,
        )

    coordinator.setRitual(ritual_id, RitualState.NON_INITIATED, 0, treasury, sender=treasury)

    with ape.reverts("Access controller for ritual must be approved"):
        coordinator.processRitualPayment(
            adopter,
            ritual_id,
            MAX_NODES,
            PACKAGE_DURATION + YELLOW_PERIOD + RED_PERIOD - 4,
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
    with ape.reverts("Only failed/expired rituals allowed to be reinitiated"):
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
    erc20, subscription, coordinator, adopter, adopter_setter, global_allow_list, treasury
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

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)
    subscription.payForSubscription(0, sender=adopter)
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
    erc20,
    subscription,
    coordinator,
    adopter,
    adopter_setter,
    global_allow_list,
    treasury,
    creator,
    chain,
):
    ritual_id = 6
    number_of_providers = 7

    with ape.reverts("Only Access Controller can call this method"):
        subscription.beforeSetAuthorization(0, [creator], True, sender=adopter)

    with ape.reverts("Ritual must be active"):
        global_allow_list.authorize(0, [creator], sender=adopter)

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)
    subscription.payForSubscription(0, sender=adopter)
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, global_allow_list.address, sender=treasury
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, DURATION, sender=treasury
    )

    with ape.reverts("Ritual must be active"):
        global_allow_list.authorize(0, [creator], sender=adopter)

    with ape.reverts("Encryptors slots filled up"):
        global_allow_list.authorize(ritual_id, [creator], sender=adopter)

    subscription.payForEncryptorSlots(2, sender=adopter)
    global_allow_list.authorize(ritual_id, [creator], sender=adopter)
    assert subscription.usedEncryptorSlots() == 1

    with ape.reverts("Encryptors slots filled up"):
        global_allow_list.authorize(ritual_id, [creator, adopter], sender=adopter)

    global_allow_list.deauthorize(ritual_id, [creator], sender=adopter)
    assert subscription.usedEncryptorSlots() == 0

    global_allow_list.authorize(ritual_id, [creator, adopter], sender=adopter)
    assert subscription.usedEncryptorSlots() == 2

    end_subscription = subscription.getEndOfSubscription()
    chain.pending_timestamp = end_subscription + 1

    with ape.reverts("Subscription has expired"):
        global_allow_list.authorize(ritual_id, [creator], sender=adopter)

    subscription.payForSubscription(0, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        global_allow_list.authorize(ritual_id, [creator], sender=adopter)

    subscription.payForEncryptorSlots(3, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        global_allow_list.authorize(ritual_id, [treasury, subscription.address], sender=adopter)
    global_allow_list.authorize(ritual_id, [treasury], sender=adopter)
    assert subscription.usedEncryptorSlots() == 3


def test_before_is_authorized(
    erc20,
    subscription,
    coordinator,
    adopter,
    adopter_setter,
    global_allow_list,
    treasury,
    creator,
    chain,
):
    ritual_id = 6

    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=adopter.private_key)
    signature = signed_digest.signature

    with ape.reverts("Only Access Controller can call this method"):
        subscription.beforeIsAuthorized(0, sender=adopter)

    with ape.reverts("Ritual must be active"):
        global_allow_list.isAuthorized(0, bytes(signature), bytes(data))

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)
    subscription.payForSubscription(1, sender=adopter)
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

    subscription.payForSubscription(0, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        global_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    subscription.payForEncryptorSlots(1, sender=adopter)
    assert global_allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))
