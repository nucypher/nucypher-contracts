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
END_DEAUTHORIZATION_SLOT = 5
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds
PENALTY_DEFAULT = 1000  # 10% penalty
PENALTY_DURATION = 60 * 60 * 24  # 1 day in seconds


def test_authorization_parameters(taco_application):
    parameters = taco_application.authorizationParameters()
    assert parameters[0] == MIN_AUTHORIZATION
    assert parameters[1] == DEAUTHORIZATION_DURATION
    assert parameters[2] == DEAUTHORIZATION_DURATION


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
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
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
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=value
        )
    ]

    # Increase authorization for staker with penalty (no confirmation)
    child_application.penalize(staking_provider, sender=staking_provider)
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 4, 2 * value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 2 * value
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == 2 * value
    assert child_application.stakingProviderInfo(staking_provider) == (2 * value, 0, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value // 4, toAmount=2 * value
        )
    ]
    chain.pending_timestamp += PENALTY_DURATION

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
    assert taco_application.authorizedOverall() == authorization
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=value, toAmount=authorization
        )
    ]

    # Increase authorization for staker with penalty
    authorization = 3 * value
    child_application.penalize(staking_provider, sender=staking_provider)
    tx = threshold_staking.authorizationIncreased(
        staking_provider, 2 * value + 1, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedOverall() == authorization * 9 // 10
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationIncreased"]
    assert events == [
        taco_application.AuthorizationIncreased(
            stakingProvider=staking_provider, fromAmount=2 * value + 1, toAmount=authorization
        )
    ]
    chain.pending_timestamp += PENALTY_DURATION

    # Emulate slash and desync by sending smaller fromAmount
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedOverall() == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
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
    child_application.penalize(staking_provider, sender=staking_provider)
    tx = threshold_staking.authorizationIncreased(
        staking_provider, value // 2, value, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedOverall() == value * 9 // 10
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
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
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)
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
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.authorizationIncreased(staking_provider, authorization, value, sender=creator)
    taco_application.involuntaryAuthorizationDecrease(
        staking_provider, value, authorization, sender=creator
    )
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)
    chain.pending_timestamp += PENALTY_DURATION

    # Prepare request to decrease before involuntary decrease
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )
    timestamp = chain.pending_timestamp - 1
    end_deauthorization = timestamp

    authorization = value // 4
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value // 2, authorization, sender=creator
    )

    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == authorization
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        authorization,
        end_deauthorization,
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
    assert taco_application.authorizedOverall() == authorization
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        authorization,
        end_deauthorization,
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
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.authorizationIncreased(staking_provider, authorization, value, sender=creator)
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, authorization, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.authorizedOverall() == authorization * 9 // 10
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (
        authorization,
        0,
        0,
    )
    chain.pending_timestamp += PENALTY_DURATION

    # Decrease everything
    tx = threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, authorization, 0, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0, 0)
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
    assert taco_application.authorizedOverall() == authorization
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)

    events = [
        event for event in tx.events if event.event_name == "AuthorizationInvoluntaryDecreased"
    ]
    assert events == [
        taco_application.AuthorizationInvoluntaryDecreased(
            stakingProvider=staking_provider, fromAmount=value, toAmount=authorization
        )
    ]

    # Another desync for staker with penalty
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.authorizationIncreased(
        staking_provider, authorization, 2 * value, sender=creator
    )
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider, value, value // 2, sender=creator
    )
    assert (
        taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == authorization
    )
    assert taco_application.authorizedOverall() == authorization * 9 // 10
    assert taco_application.authorizedStake(staking_provider) == authorization
    assert child_application.stakingProviderInfo(staking_provider) == (authorization, 0, 0)
    chain.pending_timestamp += PENALTY_DURATION


def test_authorization_decrease_request(
    accounts, threshold_staking, taco_application, child_application, chain
):
    """
    Tests for authorization method: authorizationDecreaseRequested
    """

    creator, staking_provider = accounts[0:2]
    deauthorization_duration = DEAUTHORIZATION_DURATION
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
    timestamp = chain.pending_timestamp - 1
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert (
        taco_application.pendingAuthorizationDecrease(staking_provider) == minimum_authorization + 1
    )
    end_deauthorization = timestamp
    assert (
        taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT]
        == end_deauthorization
    )
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value - minimum_authorization,
        end_deauthorization,
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
    timestamp = chain.pending_timestamp - 1
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value
    end_deauthorization = timestamp
    assert (
        taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT]
        == end_deauthorization
    )
    assert taco_application.authorizedOverall() == value
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value,
        end_deauthorization,
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

    timestamp = chain.pending_timestamp - 1
    end_deauthorization = timestamp
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value // 2
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 2
    assert taco_application.authorizedOverall() == value // 2
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        value // 2,
        value // 2,
        end_deauthorization,
    )

    events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseRequested"]
    assert events == [
        taco_application.AuthorizationDecreaseRequested(
            stakingProvider=staking_provider, fromAmount=value // 2, toAmount=0
        )
    ]

    # Emulate desync for staker with penalty
    chain.pending_timestamp += deauthorization_duration
    child_application.penalize(staking_provider, sender=staking_provider)
    child_application.release(staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == value // 2 * 9 // 10
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.authorizedOverall() == 0
    threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
    assert taco_application.authorizedOverall() == 0
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == value * 9 // 10
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value // 2, 0, sender=creator
    )
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value // 2
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 2
    assert taco_application.authorizedOverall() == value // 2 * 9 // 10
    chain.pending_timestamp += PENALTY_DURATION


def test_finish_authorization_decrease(
    accounts, threshold_staking, taco_application, child_application, chain
):
    """
    Tests for authorization method: approveAuthorizationDecreas
    """

    creator, staking_provider = accounts[0:2]
    deauthorization_duration = DEAUTHORIZATION_DURATION
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
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.authorizedOverall() == 0
    assert tx.events == [
        taco_application.AuthorizationDecreaseApproved(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Try again with penalty
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
    threshold_staking.authorizationDecreaseRequested(
        staking_provider, value, new_value, sender=creator
    )
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.authorizedOverall() == 0
    chain.pending_timestamp += PENALTY_DURATION

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
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0, 0)
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
    chain.pending_timestamp += deauthorization_duration

    # Can't approve without release
    with ape.reverts("Node has not finished leaving process"):
        taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    child_application.release(staking_provider, sender=creator)

    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedOverall() == new_value
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0, 0)
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
    chain.pending_timestamp += deauthorization_duration
    child_application.penalize(staking_provider, sender=staking_provider)
    child_application.release(staking_provider, sender=creator)
    taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.authorizedOverall() == new_value * 9 // 10
    chain.pending_timestamp += PENALTY_DURATION

    # Decrease everything
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    chain.pending_timestamp += deauthorization_duration
    tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0, 0)
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
    chain.pending_timestamp += deauthorization_duration
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
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0, 0)
    assert taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "AuthorizationReSynchronized"]
    assert events == [
        taco_application.AuthorizationReSynchronized(
            stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
        )
    ]

    # Resync again for staker with penalty
    new_value = 3 * minimum_authorization // 2
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == new_value
    chain.pending_timestamp += PENALTY_DURATION

    # Confirm operator and change authorized amount again
    value = new_value
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    new_value = minimum_authorization
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
    assert taco_application.authorizedOverall() == new_value
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedOverall() == new_value
    assert taco_application.authorizedStake(staking_provider) == new_value
    assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0, 0)
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
    child_application.penalize(staking_provider, sender=staking_provider)
    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    taco_application.resynchronizeAuthorization(staking_provider, sender=creator)
    assert taco_application.authorizedOverall() == new_value * 9 // 10
    assert taco_application.authorizedStake(staking_provider) == new_value
    chain.pending_timestamp += PENALTY_DURATION

    # Request decrease and change authorized amount again
    value = new_value
    threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
    new_value = minimum_authorization // 2
    timestamp = chain.pending_timestamp - 1
    end_deauthorization = timestamp

    threshold_staking.setAuthorized(staking_provider, new_value, sender=creator)
    tx = taco_application.resynchronizeAuthorization(staking_provider, sender=creator)

    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == new_value
    assert taco_application.authorizedOverall() == new_value
    assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
    assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
    assert taco_application.authorizedOverall() == new_value
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (
        new_value,
        new_value,
        end_deauthorization,
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
    assert taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT] == 0
    assert taco_application.authorizedOverall() == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
    assert taco_application.authorizedOverall() == 0
    assert taco_application.authorizedStake(staking_provider) == 0
    assert child_application.stakingProviderInfo(staking_provider) == (0, 0, 0)
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

    assert child_application.stakingProviderInfo(staking_provider) == (0, 0, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    # Manual sync state with child
    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
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

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
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

    assert child_application.stakingProviderInfo(staking_provider) == (value, 0, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == 0
    assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    assert child_application.stakingProviderInfo(staking_provider) == (0, 0, 0)
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
    timestamp = chain.pending_timestamp - 1
    end_deauthorization = timestamp
    child_application.updateAuthorization(staking_provider, 2 * value // 3, 0, 0, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 3
    assert (
        taco_application.stakingProviderInfo(staking_provider)[END_DEAUTHORIZATION_SLOT]
        == end_deauthorization
    )
    assert child_application.stakingProviderInfo(staking_provider) == (2 * value // 3, 0, 0)

    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
    assert taco_application.authorizedStake(staking_provider) == value
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value // 3,
        end_deauthorization,
    )
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=value,
            deauthorizing=value // 3,
            endDeauthorization=end_deauthorization,
            operator=operator,
        )
    ]
