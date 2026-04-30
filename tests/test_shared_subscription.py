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

import ape
import pytest
from ape.utils import ZERO_ADDRESS
from eth_account.messages import encode_defunct
from web3 import Web3

from tests.conftest import RitualState

ONE_DAY = 24 * 60 * 60
FEE_PACKAGES = [
    # 14 days, 15 encryptors, 150 USDC
    [14 * ONE_DAY, 15, 8267195767195],
    # 90 days, 500 encryptors, 1000 USDC
    [90 * ONE_DAY, 500, 257201646090],
    # Test "free" package
    [ONE_DAY, 1, 1],
]

ERC20_SUPPLY = 10**24


@pytest.fixture(scope="module")
def contract_owner(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def adopter(accounts):
    return accounts[2]


@pytest.fixture(scope="module")
def adopter_setter(accounts):
    return accounts[3]


@pytest.fixture(scope="module")
def auth_admin(accounts):
    return accounts[4]


@pytest.fixture()
def erc20(project, adopter):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=adopter)
    return token


@pytest.fixture()
def coordinator(project, creator):
    contract = project.CoordinatorForSharedSubscriptionMock.deploy(
        sender=creator,
    )
    return contract


@pytest.fixture()
def allow_list(project, creator, coordinator):
    contract = project.SharedAllowList.deploy(coordinator.address, sender=creator)
    return contract


@pytest.fixture()
def subscription(
    project, creator, coordinator, allow_list, erc20, adopter_setter, contract_owner, oz_dependency
):
    contract = project.SharedSubscription.deploy(
        coordinator.address,
        allow_list.address,
        erc20.address,
        adopter_setter,
        sender=creator,
    )

    encoded_initializer_function = b""
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        creator,
        encoded_initializer_function,
        sender=creator,
    )
    proxy_contract = project.SharedSubscription.at(proxy.address)
    coordinator.setFeeModel(proxy_contract.address, sender=creator)
    proxy_contract.initialize(contract_owner.address, FEE_PACKAGES, sender=contract_owner)
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


def test_get_encryptor_fee_rate(subscription):
    assert subscription.feePackages(0, 1) == 15
    assert subscription.feePackages(1, 1) == 500
    assert subscription.getEncryptorFeeRate(15, 14 * ONE_DAY) == FEE_PACKAGES[0][2]
    assert subscription.getEncryptorFeeRate(500, 90 * ONE_DAY) == FEE_PACKAGES[1][2]
    with ape.reverts("Fee package is not available"):
        subscription.getEncryptorFeeRate(15, 15 * ONE_DAY)
    with ape.reverts("Fee package is not available"):
        subscription.getEncryptorFeeRate(15, 90 * ONE_DAY)

    fees = subscription.encryptorFees(FEE_PACKAGES[0][2], 15, 14 * ONE_DAY)
    assert round(fees / 10**18, 0) == 150  # 150 USDC
    fees = subscription.encryptorFees(FEE_PACKAGES[1][2], 500, 90 * ONE_DAY)
    assert round(fees / 10**18, 0) == 1000  # 1000 USDC


def test_pay_subscription(erc20, subscription, adopter, auth_admin, chain):
    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)

    with ape.reverts("Fee package is not available"):
        subscription.payForSubscription(auth_admin, 15, 15 * ONE_DAY, sender=adopter)

    # First payment
    balance_before = erc20.balanceOf(adopter)
    tx = subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    timestamp = chain.pending_timestamp - 1
    end_subscription = timestamp + 14 * ONE_DAY

    billing = subscription.billing(auth_admin)
    assert billing.encryptorSlots == 15
    assert billing.usedEncryptorSlots == 0
    assert billing.endOfSubscription == end_subscription
    assert billing.encryptorFeeRate == FEE_PACKAGES[0][2]
    balance_after = erc20.balanceOf(adopter)
    fees = subscription.encryptorFees(FEE_PACKAGES[0][2], 15, 14 * ONE_DAY)
    assert balance_after + fees == balance_before
    assert erc20.balanceOf(subscription.address) == fees

    events = [event for event in tx.events if event.event_name == "SubscriptionPaid"]
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            authAdmin=auth_admin,
            amount=fees,
            encryptorSlots=15,
            endOfSubscription=end_subscription,
        )
    ]

    # Extend
    tx = subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    end_subscription += 14 * ONE_DAY

    billing = subscription.billing(auth_admin)
    assert billing.encryptorSlots == 15
    assert billing.usedEncryptorSlots == 0
    assert billing.endOfSubscription == end_subscription
    assert billing.encryptorFeeRate == FEE_PACKAGES[0][2]
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + 2 * fees == balance_before
    assert erc20.balanceOf(subscription.address) == 2 * fees

    events = [event for event in tx.events if event.event_name == "SubscriptionPaid"]
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            authAdmin=auth_admin,
            amount=fees,
            encryptorSlots=15,
            endOfSubscription=end_subscription,
        )
    ]

    # Extend after some time
    chain.pending_timestamp = end_subscription + ONE_DAY
    tx = subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    timestamp = chain.pending_timestamp - 1
    end_subscription = timestamp + 14 * ONE_DAY

    billing = subscription.billing(auth_admin)
    assert billing.encryptorSlots == 15
    assert billing.usedEncryptorSlots == 0
    assert billing.endOfSubscription == end_subscription
    assert billing.encryptorFeeRate == FEE_PACKAGES[0][2]
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + 3 * fees == balance_before
    assert erc20.balanceOf(subscription.address) == 3 * fees

    events = [event for event in tx.events if event.event_name == "SubscriptionPaid"]
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            authAdmin=auth_admin,
            amount=fees,
            encryptorSlots=15,
            endOfSubscription=end_subscription,
        )
    ]

    # Change package
    with ape.reverts("Renewal allowed only to later end of subscription"):
        subscription.payForSubscription(auth_admin, 1, ONE_DAY, sender=adopter)
    chain.pending_timestamp = end_subscription - ONE_DAY + 1
    with ape.reverts("Discount can not be more than new package fees"):
        subscription.payForSubscription(auth_admin, 1, ONE_DAY, sender=adopter)

    balance_before = erc20.balanceOf(adopter)
    time_left = ONE_DAY - 2
    discount = subscription.encryptorFees(
        billing.encryptorFeeRate, billing.encryptorSlots, time_left
    )
    tx = subscription.payForSubscription(auth_admin, 500, 90 * ONE_DAY, sender=adopter)
    timestamp = chain.pending_timestamp - 1
    end_subscription = timestamp + 90 * ONE_DAY

    billing = subscription.billing(auth_admin)
    assert billing.encryptorSlots == 500
    assert billing.usedEncryptorSlots == 0
    assert billing.endOfSubscription == end_subscription
    assert billing.encryptorFeeRate == FEE_PACKAGES[1][2]
    balance_after = erc20.balanceOf(adopter)
    fees = subscription.encryptorFees(
        billing.encryptorFeeRate, billing.encryptorSlots, 90 * ONE_DAY
    )
    assert balance_after + fees - discount == balance_before

    events = [event for event in tx.events if event.event_name == "SubscriptionPaid"]
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            authAdmin=auth_admin,
            amount=fees - discount,
            encryptorSlots=500,
            endOfSubscription=end_subscription,
        )
    ]


def test_withdraw(erc20, subscription, adopter, auth_admin, contract_owner):
    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)

    with ape.reverts("Insufficient balance available"):
        subscription.withdrawTokens(sender=adopter)

    subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    fees = subscription.encryptorFees(FEE_PACKAGES[0][2], 15, 14 * ONE_DAY)

    tx = subscription.withdrawTokens(sender=adopter)
    assert erc20.balanceOf(contract_owner) == fees
    assert erc20.balanceOf(subscription.address) == 0

    events = [event for event in tx.events if event.event_name == "WithdrawalTokens"]
    assert events == [subscription.WithdrawalTokens(owner=contract_owner, amount=fees)]


def test_process_ritual_payment(
    erc20, subscription, coordinator, allow_list, adopter, adopter_setter, contract_owner
):
    ritual_id = 7
    number_of_providers = 6
    duration = 100 * ONE_DAY
    subscription.setAdopter(adopter, sender=adopter_setter)

    with ape.reverts("Only the Coordinator can call this method"):
        subscription.processRitualPayment(
            adopter, ritual_id, number_of_providers, duration, sender=contract_owner
        )
    with ape.reverts("Only adopter can initiate ritual"):
        coordinator.processRitualPayment(
            contract_owner, ritual_id, number_of_providers, duration, sender=contract_owner
        )

    coordinator.setRitual(
        ritual_id, RitualState.NON_INITIATED, 0, contract_owner, sender=contract_owner
    )

    with ape.reverts("Access controller for ritual must be approved"):
        coordinator.processRitualPayment(
            adopter,
            ritual_id,
            number_of_providers,
            duration,
            sender=contract_owner,
        )

    assert subscription.activeRitualId() == subscription.INACTIVE_RITUAL_ID()
    coordinator.setRitual(
        ritual_id,
        RitualState.DKG_AWAITING_TRANSCRIPTS,
        0,
        allow_list.address,
        sender=contract_owner,
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, duration, sender=contract_owner
    )
    assert subscription.activeRitualId() == ritual_id

    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    with ape.reverts("Only failed/expired rituals allowed to be reinitiated"):
        coordinator.processRitualPayment(
            adopter, new_ritual_id, number_of_providers, duration, sender=contract_owner
        )

    coordinator.setRitual(
        ritual_id, RitualState.DKG_INVALID, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, duration, sender=contract_owner
    )
    assert subscription.activeRitualId() == new_ritual_id

    ritual_id = new_ritual_id
    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    coordinator.setRitual(
        ritual_id, RitualState.DKG_TIMEOUT, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, duration, sender=contract_owner
    )
    assert subscription.activeRitualId() == new_ritual_id

    ritual_id = new_ritual_id
    new_ritual_id = ritual_id + 1
    coordinator.setRitual(
        new_ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    coordinator.setRitual(
        ritual_id, RitualState.EXPIRED, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(
        adopter, new_ritual_id, number_of_providers, duration, sender=contract_owner
    )
    assert subscription.activeRitualId() == new_ritual_id


def test_process_ritual_extending(
    subscription, coordinator, adopter, adopter_setter, allow_list, contract_owner
):
    ritual_id = 6
    number_of_providers = 7
    duration = ONE_DAY

    with ape.reverts("Only the Coordinator can call this method"):
        subscription.processRitualExtending(
            adopter, ritual_id, number_of_providers, duration, sender=contract_owner
        )

    subscription.setAdopter(adopter, sender=adopter_setter)
    with ape.reverts("Ritual must be active"):
        coordinator.processRitualExtending(
            adopter, ritual_id, number_of_providers, duration, sender=contract_owner
        )
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, duration, sender=contract_owner
    )
    with ape.reverts("Only adopter can extend ritual"):
        coordinator.processRitualExtending(
            contract_owner, ritual_id, number_of_providers, duration, sender=contract_owner
        )

    coordinator.processRitualExtending(
        adopter, ritual_id, number_of_providers, duration, sender=adopter
    )


def test_before_set_authorization(
    erc20,
    subscription,
    coordinator,
    adopter,
    adopter_setter,
    allow_list,
    contract_owner,
    auth_admin,
    creator,
    chain,
):
    ritual_id = 6
    number_of_providers = 7
    duration = 1000 * ONE_DAY
    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.setAdopter(adopter, sender=adopter_setter)

    with ape.reverts("Only Access Controller can call this method"):
        subscription.beforeSetAuthorization(auth_admin, 0, [creator], True, sender=adopter)

    with ape.reverts("Ritual must be active"):
        allow_list.authorize(0, [creator], sender=auth_admin)

    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(
        adopter, ritual_id, number_of_providers, duration, sender=contract_owner
    )

    with ape.reverts("Ritual must be active"):
        allow_list.authorize(0, [creator], sender=auth_admin)

    with ape.reverts("Subscription has expired"):
        allow_list.authorize(ritual_id, [creator], sender=auth_admin)

    subscription.payForSubscription(auth_admin, 1, ONE_DAY, sender=adopter)
    allow_list.authorize(ritual_id, [creator], sender=auth_admin)
    billing = subscription.billing(auth_admin)
    assert billing.usedEncryptorSlots == 1

    with ape.reverts("Encryptors slots filled up"):
        allow_list.authorize(ritual_id, [creator], sender=auth_admin)

    allow_list.deauthorize(ritual_id, [creator], sender=auth_admin)
    billing = subscription.billing(auth_admin)
    assert billing.usedEncryptorSlots == 0

    with ape.reverts("Encryptors slots filled up"):
        allow_list.authorize(ritual_id, [creator, adopter], sender=auth_admin)

    subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    allow_list.authorize(ritual_id, [creator, adopter], sender=auth_admin)
    billing = subscription.billing(auth_admin)
    assert billing.usedEncryptorSlots == 2

    end_subscription = billing.endOfSubscription
    chain.pending_timestamp = end_subscription + 1

    with ape.reverts("Subscription has expired"):
        allow_list.authorize(ritual_id, [creator], sender=adopter)

    subscription.payForSubscription(auth_admin, 1, ONE_DAY, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        allow_list.authorize(ritual_id, [creator], sender=auth_admin)

    subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        allow_list.authorize(ritual_id, [contract_owner] * 14, sender=auth_admin)
    allow_list.authorize(ritual_id, [contract_owner], sender=auth_admin)
    billing = subscription.billing(auth_admin)
    assert billing.usedEncryptorSlots == 3


def test_before_is_authorized(
    erc20,
    subscription,
    coordinator,
    adopter,
    adopter_setter,
    allow_list,
    contract_owner,
    auth_admin,
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
        subscription.beforeIsAuthorized(auth_admin, 0, sender=adopter)

    erc20.approve(subscription.address, ERC20_SUPPLY, sender=adopter)
    subscription.payForSubscription(auth_admin, 15, 14 * ONE_DAY, sender=adopter)

    subscription.setAdopter(adopter, sender=adopter_setter)
    coordinator.setRitual(
        ritual_id, RitualState.ACTIVE, 0, allow_list.address, sender=contract_owner
    )
    coordinator.processRitualPayment(adopter, ritual_id, 10, ONE_DAY, sender=contract_owner)
    allow_list.authorize(ritual_id, [adopter.address, creator.address], sender=auth_admin)

    assert not allow_list.isAuthorized(0, bytes(signature), bytes(data))
    assert allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    chain.pending_timestamp += 15 * ONE_DAY

    with ape.reverts("Subscription has expired"):
        allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    subscription.payForSubscription(auth_admin, 1, ONE_DAY, sender=adopter)
    with ape.reverts("Encryptors slots filled up"):
        allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))

    allow_list.deauthorize(ritual_id, [creator], sender=auth_admin)
    assert allow_list.isAuthorized(ritual_id, bytes(signature), bytes(data))
