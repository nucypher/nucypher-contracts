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

import pytest
from eth_utils import to_checksum_address

from deployment.constants import EIP1967_ADMIN_SLOT

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
    project,
    creator,
    adopter,
    coordinator,
    global_allow_list,
    erc20,
    adopter_setter,
    treasury,
    oz_dependency,
    chain,
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
    proxy_contract = project.BqETHSubscription.at(proxy.address)
    coordinator.setFeeModel(proxy_contract.address, sender=creator)
    proxy_contract.initialize(treasury.address, sender=treasury)

    proxy_contract.setAdopter(adopter, sender=adopter_setter)
    erc20.approve(proxy_contract.address, ERC20_SUPPLY, sender=adopter)
    proxy_contract.payForSubscription(0, sender=adopter)

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
    chain.pending_timestamp = timestamp + PACKAGE_DURATION + 1

    contract = project.BqETHSubscription.deploy(
        coordinator.address,
        global_allow_list.address,
        erc20.address,
        adopter_setter,
        BASE_FEE_RATE,
        BASE_FEE_RATE_INCREASE * 100,
        ENCRYPTORS_FEE_RATE,
        MAX_NODES,
        2 * PACKAGE_DURATION,
        YELLOW_PERIOD,
        RED_PERIOD,
        sender=creator,
    )
    admin_slot = chain.provider.get_storage_at(address=proxy.address, slot=EIP1967_ADMIN_SLOT)
    admin_address = to_checksum_address(admin_slot[-20:])
    proxy_admin = oz_dependency.ProxyAdmin.at(admin_address)

    proxy_admin.upgradeAndCall(proxy.address, contract.address, b"", sender=creator)
    proxy_contract.reinitialize(sender=treasury)
    return proxy_contract


def test_pay_subscription(erc20, subscription, adopter, chain):
    timestamp = chain.pending_timestamp - 1

    # First payment
    balance_before = erc20.balanceOf(adopter)
    current_base_fee = 2 * base_fee(1)
    assert subscription.baseFees() == current_base_fee
    assert subscription.baseFees(1) == current_base_fee
    assert subscription.baseFees(2) == 2 * base_fee(2)
    assert subscription.baseFees(3) == 2 * base_fee(3)
    assert subscription.baseFees(4) == 2 * base_fee(4)
    assert subscription.startOfSubscription() == timestamp
    end_subscription = timestamp + 2 * PACKAGE_DURATION
    assert subscription.getEndOfSubscription() == end_subscription
    assert subscription.getCurrentPeriodNumber() == 1
    assert subscription.billingInfo(0) == (True, 0)
    assert subscription.billingInfo(1) == (False, 0)

    tx = subscription.payForSubscription(0, sender=adopter)
    end_subscription = timestamp + 4 * PACKAGE_DURATION
    assert subscription.startOfSubscription() == timestamp
    assert subscription.getEndOfSubscription() == end_subscription
    assert subscription.getCurrentPeriodNumber() == 1
    assert subscription.billingInfo(0) == (True, 0)
    assert subscription.billingInfo(1) == (True, 0)
    balance_after = erc20.balanceOf(adopter)
    assert balance_after + current_base_fee == balance_before

    events = subscription.SubscriptionPaid.from_receipt(tx)
    assert events == [
        subscription.SubscriptionPaid(
            subscriber=adopter,
            amount=current_base_fee,
            encryptorSlots=0,
            endOfSubscription=end_subscription,
        )
    ]
