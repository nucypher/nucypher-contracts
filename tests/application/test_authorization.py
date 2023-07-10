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

import ape
from ape.utils import ZERO_ADDRESS
from web3 import Web3

AUTHORIZATION_SLOT = 3
DEAUTHORIZING_SLOT = 4
END_DEAUTHORIZATION_SLOT = 5
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds


def test_authorization_increase(accounts, threshold_staking, pre_cbd_application):
    """
    Tests for authorization method: authorizationIncreased
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Can't call `authorizationIncreased` directly
    with ape.reverts():
        pre_cbd_application.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Staking provider and toAmount must be specified
    with ape.reverts():
        threshold_staking.authorizationIncreased(ZERO_ADDRESS, 0, value, sender=creator)

    with ape.reverts():
        threshold_staking.authorizationIncreased(staking_provider, 0, 0, sender=creator)

    # Authorization must be greater than minimum
    with ape.reverts():
        threshold_staking.authorizationIncreased(staking_provider, 0, value - 1, sender=creator)

    # First authorization
    tx = threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == value
    assert pre_cbd_application.isAuthorized(staking_provider)

    # Check that all events are emitted
    events = pre_cbd_application.AuthorizationIncreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == 0
    assert event["toAmount"] == value

    # Decrease and try to increase again
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )

    # Resulting authorization must be greater than minimum
    with ape.reverts():
        threshold_staking.authorizationIncreased(
            staking_provider, value // 2, value - 1, sender=creator
        )

    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == value
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationIncreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value // 2
    assert event["toAmount"] == value

    # Confirm operator address and try to increase authorization again
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)

    authorization = 2 * value + 1
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value, authorization, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT]
        == authorization
    )
    assert pre_cbd_application.authorizedOverall() == authorization
    assert pre_cbd_application.authorizedStake(staking_provider) == authorization
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationIncreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == authorization

    # Emulate slash and desync by sending smaller fromAmount
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert pre_cbd_application.authorizedOverall() == value
    assert pre_cbd_application.authorizedStake(staking_provider) == value
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationIncreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value // 2
    assert event["toAmount"] == value


def test_involuntary_authorization_decrease(accounts, threshold_staking, pre_cbd_application):
    """
    Tests for authorization method: involuntaryAuthorizationDecrease
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Can't call `involuntaryAuthorizationDecrease` directly
    with ape.reverts():
        pre_cbd_application.involuntaryAuthorizationDecrease(
            staking_provider, value, 0, sender=creator
        )

    authorization = value // 2
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT]
        == authorization
    )
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == authorization
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert not pre_cbd_application.isOperatorConfirmed(staking_provider)

    events = pre_cbd_application.AuthorizationInvoluntaryDecreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == authorization

    # Prepare request to decrease before involuntary decrease
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )
    authorization = value // 4
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value // 2, authorization, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT]
        == authorization
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT]
        == authorization
    )
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == authorization
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert not pre_cbd_application.isOperatorConfirmed(staking_provider)

    events = pre_cbd_application.AuthorizationInvoluntaryDecreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value // 2
    assert event["toAmount"] == authorization

    # Confirm operator address and decrease again
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)

    authorization = value // 8
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value // 4, authorization, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT]
        == authorization
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT]
        == authorization
    )
    assert pre_cbd_application.authorizedOverall() == authorization
    assert pre_cbd_application.authorizedStake(staking_provider) == authorization
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert pre_cbd_application.isOperatorConfirmed(staking_provider)
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == staking_provider
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == staking_provider

    events = pre_cbd_application.AuthorizationInvoluntaryDecreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value // 4
    assert event["toAmount"] == authorization

    # Decrease everything
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, authorization, 0, sender=creator
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == 0
    assert not pre_cbd_application.isAuthorized(staking_provider)
    assert not pre_cbd_application.isOperatorConfirmed(staking_provider)
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == ZERO_ADDRESS
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == ZERO_ADDRESS

    events = pre_cbd_application.AuthorizationInvoluntaryDecreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == authorization
    assert event["toAmount"] == 0

    # Emulate slash and desync by sending smaller fromAmount
    threshold_staking.authorizationIncreased(staking_provider, 0, 2 * value, sender=creator)
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)

    authorization = value // 2
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT]
        == authorization
    )
    assert pre_cbd_application.authorizedOverall() == authorization
    assert pre_cbd_application.authorizedStake(staking_provider) == authorization

    events = pre_cbd_application.AuthorizationInvoluntaryDecreased.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == authorization


def test_authorization_decrease_request(accounts, threshold_staking, pre_cbd_application, chain):
    """
    Tests for authorization method: authorizationDecreaseRequested
    """

    creator, staking_provider = accounts[0:2]
    deauthorization_duration = DEAUTHORIZATION_DURATION
    minimum_authorization = MIN_AUTHORIZATION
    value = 2 * minimum_authorization + 1

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Can't call `involuntaryAuthorizationDecrease` directly
    with ape.reverts():
        pre_cbd_application.authorizationDecreaseRequested(
            staking_provider, value, 0, sender=creator
        )

    # Can't increase amount using request
    with ape.reverts():
        threshold_staking.authorizationDecreaseRequested(
            staking_provider, value, value + 1, sender=creator
        )

    # Resulting amount must be greater than minimum or 0
    with ape.reverts():
        threshold_staking.authorizationDecreaseRequested(staking_provider, value, 1, sender=creator)

    # Request of partial decrease
    tx = threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, minimum_authorization, sender=creator
    )
    timestamp = chain.pending_timestamp - 1
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT]
        == minimum_authorization + 1
    )
    end_deauthorization = timestamp + deauthorization_duration
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT]
        == end_deauthorization
    )
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == value
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationDecreaseRequested.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == minimum_authorization

    # Confirm operator address and request full decrease
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)

    tx = threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, 0, sender=creator
    )
    timestamp = chain.pending_timestamp - 1
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == value
    end_deauthorization = timestamp + deauthorization_duration
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT]
        == end_deauthorization
    )
    assert pre_cbd_application.authorizedOverall() == value
    assert pre_cbd_application.authorizedStake(staking_provider) == value
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationDecreaseRequested.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == 0

    # Emulate slash and desync by sending smaller fromAmount
    tx = threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value // 2
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == value // 2
    )
    assert pre_cbd_application.authorizedOverall() == value // 2
    assert pre_cbd_application.authorizedStake(staking_provider) == value // 2

    events = pre_cbd_application.AuthorizationDecreaseRequested.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value // 2
    assert event["toAmount"] == 0


def test_finish_authorization_decrease(accounts, threshold_staking, pre_cbd_application, chain):
    """
    Tests for authorization method: finishAuthorizationDecrease
    """

    creator, staking_provider = accounts[0:2]
    deauthorization_duration = DEAUTHORIZATION_DURATION
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Can't approve decrease without request
    with ape.reverts():
        pre_cbd_application.finishAuthorizationDecrease(staking_provider, sender=creator)

    new_value = 2 * minimum_authorization
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, new_value, sender=creator
    )

    # Can't approve decrease before end timestamp
    with ape.reverts():
        pre_cbd_application.finishAuthorizationDecrease(staking_provider, sender=creator)

    # Wait some time
    chain.pending_timestamp += deauthorization_duration
    tx = pre_cbd_application.finishAuthorizationDecrease(staking_provider, sender=creator)
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == new_value
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert (
        threshold_staking.authorizedStake(staking_provider, pre_cbd_application.address)
        == new_value
    )

    events = pre_cbd_application.AuthorizationDecreaseApproved.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == new_value

    # Confirm operator, request again then desync values and finish decrease
    value = new_value
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, minimum_authorization, sender=creator
    )

    new_value = minimum_authorization // 2
    threshold_staking.setDecreaseRequest(staking_provider, new_value, sender=creator)
    chain.pending_timestamp += deauthorization_duration
    tx = pre_cbd_application.finishAuthorizationDecrease(staking_provider, sender=creator)

    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == staking_provider
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == staking_provider
    assert pre_cbd_application.authorizedOverall() == new_value
    assert pre_cbd_application.authorizedStake(staking_provider) == new_value
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert pre_cbd_application.isOperatorConfirmed(staking_provider)
    assert (
        threshold_staking.authorizedStake(staking_provider, pre_cbd_application.address)
        == new_value
    )

    events = pre_cbd_application.AuthorizationDecreaseApproved.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == new_value

    # Decrease everything
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    chain.pending_timestamp += deauthorization_duration
    tx = pre_cbd_application.finishAuthorizationDecrease(staking_provider, sender=creator)

    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == ZERO_ADDRESS
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == ZERO_ADDRESS
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == 0
    assert not pre_cbd_application.isAuthorized(staking_provider)
    assert not pre_cbd_application.isOperatorConfirmed(staking_provider)
    assert threshold_staking.authorizedStake(staking_provider, pre_cbd_application.address) == 0

    events = pre_cbd_application.AuthorizationDecreaseApproved.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == 0


def test_resync(accounts, threshold_staking, pre_cbd_application):
    """
    Tests for authorization method: resynchronizeAuthorization
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Nothing sync for not staking provider
    with ape.reverts():
        pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Nothing to resync
    with ape.reverts():
        pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)

    # Change authorized amount and resync
    new_value = 2 * minimum_authorization
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    )
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == new_value
    assert pre_cbd_application.isAuthorized(staking_provider)

    events = pre_cbd_application.AuthorizationReSynchronized.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == new_value

    # Confirm operator and change authorized amount again
    value = new_value
    pre_cbd_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    pre_cbd_application.confirmOperatorAddress(sender=staking_provider)

    new_value = minimum_authorization
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    )
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.authorizedOverall() == new_value
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == staking_provider
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == staking_provider
    assert pre_cbd_application.authorizedOverall() == new_value
    assert pre_cbd_application.authorizedStake(staking_provider) == new_value
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert pre_cbd_application.isOperatorConfirmed(staking_provider)

    events = pre_cbd_application.AuthorizationReSynchronized.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == new_value

    # Request decrease and change authorized amount again
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    new_value = minimum_authorization // 2

    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    )
    assert (
        pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == new_value
    )
    assert pre_cbd_application.authorizedOverall() == new_value
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == staking_provider
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == staking_provider
    assert pre_cbd_application.authorizedOverall() == new_value
    assert pre_cbd_application.authorizedStake(staking_provider) == new_value
    assert pre_cbd_application.isAuthorized(staking_provider)
    assert pre_cbd_application.isOperatorConfirmed(staking_provider)

    events = pre_cbd_application.AuthorizationReSynchronized.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == new_value

    # Set authorized amount to zero and resync again
    value = new_value
    threshold_staking.setAuthorized(staking_provider, 0, sender=creator)
    tx = pre_cbd_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert pre_cbd_application.stakingProviderInfo(staking_provider)[DEAUTHORIZING_SLOT] == 0
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.getOperatorFromStakingProvider(staking_provider) == ZERO_ADDRESS
    assert pre_cbd_application.stakingProviderFromOperator(staking_provider) == ZERO_ADDRESS
    assert pre_cbd_application.authorizedOverall() == 0
    assert pre_cbd_application.authorizedStake(staking_provider) == 0
    assert not pre_cbd_application.isAuthorized(staking_provider)
    assert not pre_cbd_application.isOperatorConfirmed(staking_provider)

    events = pre_cbd_application.AuthorizationReSynchronized.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["fromAmount"] == value
    assert event["toAmount"] == 0
