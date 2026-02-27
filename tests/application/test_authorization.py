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

OPERATOR_CONFIRMED_SLOT = 1
AUTHORIZATION_SLOT = 3
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")


def test_authorization_parameters(taco_application):
    parameters = taco_application.authorizationParameters()
    assert parameters[0] == MIN_AUTHORIZATION
    assert parameters[1] == 0
    assert parameters[2] == 0


def test_authorization_increase(
    accounts, threshold_staking, taco_application, child_application, chain
):
    """
    Tests for authorization method: authorizationIncreased
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Can't call `authorizationIncreased` directly
    with ape.reverts():
        taco_application.authorizationIncreased(staking_provider, 0, value, sender=staking_provider)

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
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)

    # Check that all events are emitted
    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=0, toAmount=value
        )
    ]

    # Decrease and try to increase again
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )

    # Resulting authorization must be greater than minimum
    with ape.reverts():
        threshold_staking.authorizationIncreased(
            staking_provider, value // 2, value - 1, sender=creator
        )

    tx = taco_application.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=value
        )
    ]

    # Increase authorization for staker (no confirmation)
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 4, 2 * value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 2 * value
    assert taco_application.authorizedStake(staking_provider) == 2 * value
    assert child_application.stakingProviderInfo(staking_provider) == (2 * value, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 4, toAmount=2 * value
        )
    ]

    # Confirm operator address and try to increase authorization again
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    authorization = 2 * value + 1
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value, toAmount=authorization
        )
    ]

    # Increase authorization for staker with penalty
    authorization = 3 * value
    tx = threshold_staking.authorizationIncreased(
        staking_provider, 2 * value + 1, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=2 * value + 1, toAmount=authorization
        )
    ]

    # Emulate slash and desync by sending smaller fromAmount
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=value
        )
    ]

    # Desync again for staker with penalty
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value, authorization, sender=creator
    )
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=value
        )
    ]


def test_involuntary_authorization_decrease(
    accounts, threshold_staking, taco_application, child_application, chain
):
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
        taco_application.involuntaryAuthorizationDecrease(
            staking_provider, value, 0, sender=staking_provider
        )

    authorization = value // 2
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)
    assert taco_application.isAuthorized(staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)
    assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=value, toAmount=authorization
        )
    ]

    # Decrease again for staker with penalty
    threshold_staking.authorizationIncreased(staking_provider, authorization, value, sender=creator)
    taco_application.involuntaryAuthorizationDecrease(
        staking_provider, value, authorization, sender=creator
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)

    # Prepare request to decrease before involuntary decrease
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )

    authorization = value // 4
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value // 2, authorization, sender=creator
    )

    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == authorization
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        authorization,
    )
    assert taco_application.isAuthorized(staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)
    assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=authorization
        )
    ]

    # Confirm operator address and decrease again
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    authorization = value // 8
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value // 4, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == authorization
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        authorization,
    )
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.isOperatorConfirmed(staking_provider)
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert child_application.stakingProviderToOperator(staking_provider) == staking_provider

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=value // 4, toAmount=authorization
        )
    ]

    # Decrease again for staker with penalty
    threshold_staking.authorizationIncreased(staking_provider, authorization, value, sender=creator)
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        0,
    )

    # Decrease everything
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, authorization, 0, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert not taco_application.isAuthorized(staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)
    assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=authorization, toAmount=0
        )
    ]

    # Emulate slash and desync by sending smaller fromAmount
    threshold_staking.authorizationIncreased(staking_provider, 0, 2 * value, sender=creator)
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    authorization = value // 2
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=value, toAmount=authorization
        )
    ]

    # Another desync for staker with penalty
    threshold_staking.authorizationIncreased(
        staking_provider, authorization, 2 * value, sender=creator
    )
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0)


def test_authorization_decrease_request(
    accounts, threshold_staking, taco_application, child_application, chain
):
    """
    Tests for authorization method: authorizationDecreaseRequested
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = 2 * minimum_authorization + 1

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Can't call `authorizationDecreaseRequested` directly
    with ape.reverts():
        taco_application.authorizationDecreaseRequested(
            staking_provider, value, 0, sender=staking_provider
        )

    # Can't increase amount using request
    with ape.reverts():
        threshold_staking.authorizationDecreaseRequested(
            staking_provider, value, value + 1, sender=creator
        )

    # Resulting amount must be greater than minimum or 0
    with ape.reverts():
        threshold_staking.authorizationDecreaseRequested(staking_provider, value, 1, sender=creator)

    assert taco_application.remainingAuthorizationDecreaseDelay(staking_provider) == 0

    # Request of partial decrease
    tx = threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, minimum_authorization, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert (
        taco_application.pendingAuthorizationDecrease(staking_provider) == minimum_authorization + 1
    )
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value - minimum_authorization,
    )
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseRequested"]
    assert events == [
        taco_application.AuthorizationDecreaseRequested(
            stakingProvider=staking_provider, fromAmount=value, toAmount=minimum_authorization
        )
    ]

    assert not child_application.stakingProviderReleased(staking_provider)
    assert not taco_application.stakingProviderReleased(staking_provider)

    # Confirm operator address and request full decrease
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    tx = taco_application.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value,
    )
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseRequested"]
    assert events == [
        taco_application.AuthorizationDecreaseRequested(
            stakingProvider=staking_provider, fromAmount=value, toAmount=0
        )
    ]

    assert child_application.stakingProviderReleased(staking_provider)
    assert taco_application.stakingProviderReleased(staking_provider)

    # Emulate slash and desync by sending smaller fromAmount
    tx = threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value // 2
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 2
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        value // 2,
        value // 2,
    )

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseRequested"]
    assert events == [
        taco_application.AuthorizationDecreaseRequested(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=0
        )
    ]

    # Emulate desync for staker with penalty
    child_application.release(staking_provider, sender=staking_provider)
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value // 2
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 2


def test_finish_authorization_decrease(
    accounts, threshold_staking, taco_application, child_application, chain
):
    """
    Tests for authorization method: approveAuthorizationDecreas
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Can't approve decrease without request
    with ape.reverts("There is no deauthorizing in process"):
        taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    new_value = 2 * minimum_authorization
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, new_value, sender=creator
    )

    # If operator never bonded then decrease can be instant
    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert tx.events == [
        taco_application.AuthorizationDecreaseApproved(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Try again with penalty
    threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, new_value, sender=creator
    )
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    # Bond operator and request decrease again
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, new_value, sender=creator
    )

    # Wait some time
    assert taco_application.remainingAuthorizationDecreaseDelay(staking_provider) == 0
    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
    assert taco_application.isAuthorized(staking_provider)
    assert (
        threshold_staking.authorizedStake(staking_provider, taco_application.address) == new_value
    )

    assert tx.events == [
        taco_application.AuthorizationDecreaseApproved(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Confirm operator, request again then desync values and finish decrease
    value = new_value
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, minimum_authorization, sender=creator
    )

    new_value = minimum_authorization // 2
    threshold_staking.setDecreaseRequest(staking_provider, new_value, sender=creator)

    # Can't approve without release
    with ape.reverts("Node has not finished leaving process"):
        taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    child_application.release(staking_provider, sender=creator)

    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.isOperatorConfirmed(staking_provider)
    assert (
        threshold_staking.authorizedStake(staking_provider, taco_application.address) == new_value
    )
    assert child_application.stakingProviderToOperator(staking_provider) == staking_provider

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseApproved"]
    assert events == [
        taco_application.AuthorizationDecreaseApproved(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Decrease again for staker with penalty
    threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, minimum_authorization, sender=creator
    )
    threshold_staking.setDecreaseRequest(staking_provider, new_value, sender=creator)
    child_application.release(staking_provider, sender=creator)
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value

    # Decrease everything
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert not taco_application.isAuthorized(staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)
    assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
    assert threshold_staking.authorizedStake(staking_provider, taco_application.address) == 0
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseApproved"]
    assert events == [
        taco_application.AuthorizationDecreaseApproved(
            stakingProvider=staking_provider, fromAmount=value, toAmount=0
        )
    ]

    # Decrease everything again
    value = minimum_authorization
    threshold_staking.authorizationIncreased(staking_provider, 0, 2 * value, sender=creator)
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, 2 * value, value, sender=creator
    )
    threshold_staking.setDecreaseRequest(staking_provider, 0, sender=creator)
    child_application.release(staking_provider, sender=creator)
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS


def test_resync(accounts, threshold_staking, taco_application, child_application, chain):
    """
    Tests for authorization method: resynchronizeAuthorization
    """

    creator, staking_provider = accounts[0:2]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Nothing sync for not staking provider
    with ape.reverts():
        taco_application.resynchronizeAuthorization(staking_provider, sender=creator)

    # Prepare staking providers
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    # Nothing to resync
    with ape.reverts():
        taco_application.resynchronizeAuthorization(staking_provider, sender=creator)

    # Change authorized amount and resync
    new_value = 2 * minimum_authorization
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationReSynchronized"]
    assert events == [
        taco_application.AuthorizationReSynchronized(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Resync again for staker with penalty
    new_value = 3 * minimum_authorization // 2
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == new_value

    # Confirm operator and change authorized amount again
    value = new_value
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    new_value = minimum_authorization
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.isOperatorConfirmed(staking_provider)
    assert child_application.stakingProviderToOperator(staking_provider) == staking_provider

    events = [event for event in tx.events if event.event_name == "AuthorizationReSynchronized"]
    assert events == [
        taco_application.AuthorizationReSynchronized(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Resync again for staker with penalty
    new_value = 3 * minimum_authorization // 4
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == new_value

    # Request decrease and change authorized amount again
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    new_value = minimum_authorization // 2

    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == new_value
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        new_value,
        new_value,
    )
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.isOperatorConfirmed(staking_provider)
    assert child_application.stakingProviderToOperator(staking_provider) == staking_provider

    events = [event for event in tx.events if event.event_name == "AuthorizationReSynchronized"]
    assert events == [
        taco_application.AuthorizationReSynchronized(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Set authorized amount to zero and resync again
    value = new_value
    threshold_staking.setAuthorized(staking_provider, 0, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert not taco_application.isAuthorized(staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)
    assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

    events = [event for event in tx.events if event.event_name == "AuthorizationReSynchronized"]
    assert events == [
        taco_application.AuthorizationReSynchronized(
            stakingProvider=staking_provider, fromAmount=value, toAmount=0
        )
    ]


def test_child_sync(accounts, threshold_staking, taco_application, child_application, chain):
    """
    Tests for x-chain method: manualChildSynchronization
    """

    creator, staking_provider, operator = accounts[0:3]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Can't sync zero address
    with ape.reverts("Staking provider must be specified"):
        taco_application.manualChildSynchronization(ZERO_ADDRESS, sender=creator)

    # Prepare staking providers with sync issues
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
    child_application.updateAuthorization(staking_provider, 0, 0, 0, sender=creator)
    child_application.updateOperator(staking_provider, ZERO_ADDRESS, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    # Manual sync state with child
    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=value,
            deauthorizing=0,
            endDeauthorization=0,
            operator=operator,
        )
    ]

    # Nothing happens in case of no issues with the bridge
    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=value,
            deauthorizing=0,
            endDeauthorization=0,
            operator=operator,
        )
    ]

    # Desync again and sync zero state
    threshold_staking.involuntaryAuthorizationDecrease(staking_provider, value, 0, sender=creator)
    child_application.updateAuthorization(staking_provider, value, 0, 0, sender=creator)
    child_application.updateOperator(staking_provider, operator, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=0,
            deauthorizing=0,
            endDeauthorization=0,
            operator=ZERO_ADDRESS,
        )
    ]

    # Desync again and sync deauthorizaing values
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, 2 * value // 3, sender=creator
    )
    child_application.updateAuthorization(staking_provider, 2 * value // 3, 0, 0, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 3
    assert child_application.stakingProviderInfo(staking_provider) == (2 * value // 3, 0)

    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value // 3,
    )
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=value,
            deauthorizing=value // 3,
            endDeauthorization=0,
            operator=operator,
        )
    ]


def test_batch_migrate(accounts, threshold_staking, taco_application, child_application, chain):
    """
    Tests for method: batchMigrateFromThreshold
    """

    (
        creator,
        staking_provider,
        staking_provider_2,
        staking_provider_3,
        owner,
        beneficiary,
        authorizer,
    ) = accounts[:7]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Not owner
    with ape.reverts():
        taco_application.batchMigrateFromThreshold([staking_provider], sender=staking_provider)

    # Nothing to migrate
    with ape.reverts("Not an active staker"):
        taco_application.batchMigrateFromThreshold([staking_provider], sender=creator)
    with ape.reverts("Array is empty"):
        taco_application.batchMigrateFromThreshold([], sender=creator)

    threshold_staking.setRoles(staking_provider, owner, beneficiary, authorizer, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    assert taco_application.rolesOf(staking_provider) == (ZERO_ADDRESS, ZERO_ADDRESS)
    tx = taco_application.batchMigrateFromThreshold([staking_provider], sender=creator)
    assert taco_application.rolesOf(staking_provider) == (owner, beneficiary)
    assert taco_application.authorizedStake(staking_provider) == minimum_authorization
    assert (
        threshold_staking.authorizedStake(staking_provider, taco_application.address)
        == minimum_authorization
    )
    assert child_application.stakingProviderInfo(staking_provider) == (minimum_authorization, 0)

    assert tx.events == [
        taco_application.Migrated(
            stakingProvider=staking_provider,
            authorized=minimum_authorization,
            stakeless=False,
        )
    ]

    threshold_staking.setRoles(staking_provider_2, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    threshold_staking.setRoles(staking_provider_3, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_3, 0, value, sender=creator)
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_3, value, minimum_authorization // 2, sender=creator
    )

    child_application.release(staking_provider_2, sender=staking_provider_2)

    with ape.reverts("Not an active staker"):
        taco_application.batchMigrateFromThreshold(
            [staking_provider, staking_provider_2, staking_provider_3], sender=creator
        )

    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    threshold_staking.setStakeless(staking_provider_3, True, sender=staking_provider_3)
    tx = taco_application.batchMigrateFromThreshold(
        [staking_provider, staking_provider_2, staking_provider_3], sender=creator
    )
    assert taco_application.rolesOf(staking_provider) == (owner, beneficiary)
    assert taco_application.rolesOf(staking_provider_2) == (staking_provider_2, staking_provider_2)
    assert taco_application.rolesOf(staking_provider_3) == (staking_provider_3, staking_provider_3)
    assert taco_application.authorizedStake(staking_provider) == minimum_authorization
    assert taco_application.authorizedStake(staking_provider_2) == minimum_authorization
    assert taco_application.authorizedStake(staking_provider_3) == minimum_authorization // 2
    assert (
        threshold_staking.authorizedStake(staking_provider, taco_application.address)
        == minimum_authorization
    )
    assert (
        threshold_staking.authorizedStake(staking_provider_2, taco_application.address)
        == minimum_authorization
    )
    assert (
        threshold_staking.authorizedStake(staking_provider_3, taco_application.address)
        == minimum_authorization // 2
    )
    assert child_application.stakingProviderInfo(staking_provider_2) == (minimum_authorization, 0)
    assert child_application.stakingProviderInfo(staking_provider_3) == (
        minimum_authorization // 2,
        0,
    )

    assert tx.events == [
        taco_application.Migrated(
            stakingProvider=staking_provider_2,
            authorized=minimum_authorization,
            stakeless=False,
        ),
        taco_application.Migrated(
            stakingProvider=staking_provider_3,
            authorized=minimum_authorization // 2,
            stakeless=True,
        ),
    ]


def test_batch_release(accounts, threshold_staking, taco_application, child_application):
    """
    Tests for method: releaseStakers
    """

    (
        creator,
        staking_provider,
        staking_provider_2,
        staking_provider_3,
        owner,
        beneficiary,
        authorizer,
    ) = accounts[:7]
    minimum_authorization = MIN_AUTHORIZATION
    value = 3 * minimum_authorization

    # Not owner
    with ape.reverts():
        taco_application.releaseStakers([staking_provider], sender=staking_provider)

    # Nothing to migrate
    with ape.reverts("Array is empty"):
        taco_application.releaseStakers([], sender=creator)

    threshold_staking.setRoles(staking_provider, owner, beneficiary, authorizer, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

    tx = taco_application.releaseStakers([staking_provider], sender=creator)
    assert taco_application.authorizedStake(staking_provider) == 0
    assert threshold_staking.authorizedStake(staking_provider, taco_application.address) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert taco_application.stakingProviderReleased(staking_provider)

    assert tx.events == [
        taco_application.Released(
            stakingProvider=staking_provider,
        )
    ]

    threshold_staking.setRoles(staking_provider_2, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_2, 0, value, sender=creator)
    threshold_staking.setRoles(staking_provider_3, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider_3, 0, value, sender=creator)
    threshold_staking.involuntaryAuthorizationDecrease(staking_provider_3, value, 0, sender=creator)
    taco_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    child_application.confirmOperatorAddress(staking_provider_2, sender=staking_provider_2)

    tx = taco_application.releaseStakers(
        [staking_provider, staking_provider_2, staking_provider_3], sender=creator
    )
    assert taco_application.authorizedStake(staking_provider) == 0
    assert taco_application.authorizedStake(staking_provider_2) == 0
    assert taco_application.authorizedStake(staking_provider_3) == 0
    assert threshold_staking.authorizedStake(staking_provider, taco_application.address) == 0
    assert threshold_staking.authorizedStake(staking_provider_2, taco_application.address) == 0
    assert threshold_staking.authorizedStake(staking_provider_3, taco_application.address) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert child_application.stakingProviderInfo(staking_provider_2) == (0, 0)
    assert child_application.stakingProviderInfo(staking_provider_3) == (0, 0)
    assert taco_application.stakingProviderToOperator(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_2) == ZERO_ADDRESS
    assert not taco_application.isOperatorConfirmed(staking_provider_2)

    assert tx.events == [
        taco_application.Released(
            stakingProvider=staking_provider_2,
        ),
    ]
