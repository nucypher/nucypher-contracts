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
from eth_utils import to_checksum_address, to_int
from web3 import Web3

OPERATOR_CONFIRMED_SLOT = 1
AUTHORIZATION_SLOT = 3
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")


def test_initialize_stake(accounts, token, taco_application, child_application):
    """
    Tests for authorization method: initializeStake
    """

    creator, staking_provider, owner, beneficiary = accounts[0:4]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Only owner of the contract can call the method
    with ape.reverts():
        taco_application.initializeStake(
            staking_provider, owner, beneficiary, sender=staking_provider
        )

    token.transfer(owner, value, sender=creator)
    token.approve(taco_application.address, value, sender=owner)
    tx = taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)
    assert token.balanceOf(taco_application.address) == value
    assert token.balanceOf(owner) == 0

    # Check that all events are emitted
    events = [event for event in tx.events if event.event_name == "Staked"]
    assert events == [
        taco_application.Staked(
            stakingProvider=staking_provider, owner=owner, beneficiary=beneficiary, amount=value
        )
    ]

    with ape.reverts("Stake already initialized"):
        taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)


def test_request_unstake(accounts, taco_application, child_application, token):
    """
    Tests for authorization method: requestUnstake
    """

    creator, staking_provider, owner, beneficiary = accounts[0:4]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Prepare staking providers
    token.transfer(owner, value, sender=creator)
    token.approve(taco_application.address, value, sender=owner)
    taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)

    # Only staking provider or owner of stake can call
    with ape.reverts("Not owner or provider"):
        taco_application.requestUnstake(staking_provider, sender=creator)

    # Request of unstaking
    tx = taco_application.requestUnstake(staking_provider, sender=staking_provider)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        0,
    )
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.eligibleStake(staking_provider) == 0

    events = [event for event in tx.events if event.event_name == "requestUnstake"]
    assert events == [taco_application.requestUnstake(stakingProvider=staking_provider)]

    assert child_application.stakingProviderReleased(staking_provider)
    assert taco_application.stakingProviderReleased(staking_provider)

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


# def test_finish_authorization_decrease(accounts, taco_application, child_application, chain):
#     """
#     Tests for authorization method: approveAuthorizationDecreas
#     """

#     creator, staking_provider = accounts[0:2]
#     minimum_authorization = MIN_AUTHORIZATION
#     value = 3 * minimum_authorization

#     # Prepare staking providers
#     threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)

#     # Can't approve decrease without request
#     with ape.reverts("There is no deauthorizing in process"):
#         taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

#     new_value = 2 * minimum_authorization
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, new_value, sender=creator
#     )

#     # If operator never bonded then decrease can be instant
#     tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
#     assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
#     assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
#     assert tx.events == [
#         taco_application.AuthorizationDecreaseApproved(
#             stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
#         )
#     ]

#     # Try again with penalty
#     threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, new_value, sender=creator
#     )
#     taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

#     # Bond operator and request decrease again
#     taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
#     threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, new_value, sender=creator
#     )

#     # Wait some time
#     assert taco_application.remainingAuthorizationDecreaseDelay(staking_provider) == 0
#     tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
#     assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
#     assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
#     assert taco_application.authorizedStake(staking_provider) == new_value
#     assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
#     assert taco_application.isAuthorized(staking_provider)
#     assert (
#         threshold_staking.authorizedStake(staking_provider, taco_application.address) == new_value
#     )

#     assert tx.events == [
#         taco_application.AuthorizationDecreaseApproved(
#             stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
#         )
#     ]

#     # Confirm operator, request again then desync values and finish decrease
#     value = new_value
#     child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, minimum_authorization, sender=creator
#     )

#     new_value = minimum_authorization // 2
#     threshold_staking.setDecreaseRequest(staking_provider, new_value, sender=creator)

#     # Can't approve without release
#     with ape.reverts("Node has not finished leaving process"):
#         taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

#     child_application.release(staking_provider, sender=creator)

#     tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

#     assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value
#     assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
#     assert taco_application.stakingProviderToOperator(staking_provider) == staking_provider
#     assert taco_application.operatorToStakingProvider(staking_provider) == staking_provider
#     assert taco_application.authorizedStake(staking_provider) == 0
#     assert child_application.stakingProviderInfo(staking_provider) == (new_value, 0)
#     assert taco_application.isAuthorized(staking_provider)
#     assert taco_application.isOperatorConfirmed(staking_provider)
#     assert (
#         threshold_staking.authorizedStake(staking_provider, taco_application.address) == new_value
#     )
#     assert child_application.stakingProviderToOperator(staking_provider) == staking_provider

#     events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseApproved"]
#     assert events == [
#         taco_application.AuthorizationDecreaseApproved(
#             stakingProvider=staking_provider, fromAmount=value, toAmount=new_value
#         )
#     ]

#     # Decrease again for staker with penalty
#     threshold_staking.authorizationIncreased(staking_provider, new_value, value, sender=creator)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, minimum_authorization, sender=creator
#     )
#     threshold_staking.setDecreaseRequest(staking_provider, new_value, sender=creator)
#     child_application.release(staking_provider, sender=creator)
#     taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
#     assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == new_value

#     # Decrease everything
#     value = new_value
#     threshold_staking.authorizationDecreaseRequested(staking_provider, value, 0, sender=creator)
#     tx = taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)

#     assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
#     assert taco_application.pendingAuthorizationDecrease(staking_provider) == 0
#     assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
#     assert taco_application.operatorToStakingProvider(staking_provider) == ZERO_ADDRESS
#     assert taco_application.authorizedStake(staking_provider) == 0
#     assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
#     assert not taco_application.isAuthorized(staking_provider)
#     assert not taco_application.isOperatorConfirmed(staking_provider)
#     assert not taco_application.stakingProviderInfo(staking_provider)[OPERATOR_CONFIRMED_SLOT]
#     assert threshold_staking.authorizedStake(staking_provider, taco_application.address) == 0
#     assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS

#     events = [event for event in tx.events if event.event_name == "AuthorizationDecreaseApproved"]
#     assert events == [
#         taco_application.AuthorizationDecreaseApproved(
#             stakingProvider=staking_provider, fromAmount=value, toAmount=0
#         )
#     ]

#     # Decrease everything again
#     value = minimum_authorization
#     threshold_staking.authorizationIncreased(staking_provider, 0, 2 * value, sender=creator)
#     taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
#     child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, 2 * value, value, sender=creator
#     )
#     threshold_staking.setDecreaseRequest(staking_provider, 0, sender=creator)
#     child_application.release(staking_provider, sender=creator)
#     taco_application.approveAuthorizationDecrease(staking_provider, sender=creator)
#     assert taco_application.authorizedStake(staking_provider) == 0
#     assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS


# def test_child_sync(accounts, taco_application, child_application, chain):
#     """
#     Tests for x-chain method: manualChildSynchronization
#     """

#     creator, staking_provider, operator = accounts[0:3]
#     minimum_authorization = MIN_AUTHORIZATION
#     value = 3 * minimum_authorization

#     # Can't sync zero address
#     with ape.reverts("Staking provider must be specified"):
#         taco_application.manualChildSynchronization(ZERO_ADDRESS, sender=creator)

#     # Prepare staking providers with sync issues
#     threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
#     taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
#     child_application.updateAuthorization(staking_provider, 0, 0, 0, sender=creator)
#     child_application.updateOperator(staking_provider, ZERO_ADDRESS, sender=creator)

#     assert taco_application.authorizedStake(staking_provider) == value
#     assert taco_application.stakingProviderToOperator(staking_provider) == operator
#     assert taco_application.operatorToStakingProvider(operator) == staking_provider

#     assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
#     assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
#     assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

#     # Manual sync state with child
#     tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

#     assert taco_application.authorizedStake(staking_provider) == value
#     assert taco_application.stakingProviderToOperator(staking_provider) == operator
#     assert taco_application.operatorToStakingProvider(operator) == staking_provider

#     assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
#     assert child_application.stakingProviderToOperator(staking_provider) == operator
#     assert child_application.operatorToStakingProvider(operator) == staking_provider

#     assert tx.events == [
#         taco_application.ManualChildSynchronizationSent(
#             stakingProvider=staking_provider,
#             authorized=value,
#             deauthorizing=0,
#             endDeauthorization=0,
#             operator=operator,
#         )
#     ]

#     # Nothing happens in case of no issues with the bridge
#     tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

#     assert taco_application.authorizedStake(staking_provider) == value
#     assert taco_application.stakingProviderToOperator(staking_provider) == operator
#     assert taco_application.operatorToStakingProvider(operator) == staking_provider

#     assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
#     assert child_application.stakingProviderToOperator(staking_provider) == operator
#     assert child_application.operatorToStakingProvider(operator) == staking_provider

#     assert tx.events == [
#         taco_application.ManualChildSynchronizationSent(
#             stakingProvider=staking_provider,
#             authorized=value,
#             deauthorizing=0,
#             endDeauthorization=0,
#             operator=operator,
#         )
#     ]

#     # Desync again and sync zero state
#     threshold_staking.involuntaryAuthorizationDecrease(staking_provider, value, 0, sender=creator)
#     child_application.updateAuthorization(staking_provider, value, 0, 0, sender=creator)
#     child_application.updateOperator(staking_provider, operator, sender=creator)
#     assert taco_application.authorizedStake(staking_provider) == 0
#     assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
#     assert taco_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

#     assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
#     assert child_application.stakingProviderToOperator(staking_provider) == operator
#     assert child_application.operatorToStakingProvider(operator) == staking_provider

#     tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
#     assert taco_application.authorizedStake(staking_provider) == 0
#     assert taco_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
#     assert taco_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

#     assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
#     assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
#     assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

#     assert tx.events == [
#         taco_application.ManualChildSynchronizationSent(
#             stakingProvider=staking_provider,
#             authorized=0,
#             deauthorizing=0,
#             endDeauthorization=0,
#             operator=ZERO_ADDRESS,
#         )
#     ]

#     # Desync again and sync deauthorizaing values
#     threshold_staking.authorizationIncreased(staking_provider, 0, value, sender=creator)
#     taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
#     threshold_staking.authorizationDecreaseRequested(
#         staking_provider, value, 2 * value // 3, sender=creator
#     )
#     child_application.updateAuthorization(staking_provider, 2 * value // 3, 0, 0, sender=creator)

#     assert taco_application.authorizedStake(staking_provider) == value
#     assert taco_application.pendingAuthorizationDecrease(staking_provider) == value // 3
#     assert child_application.stakingProviderInfo(staking_provider) == (2 * value // 3, 0)

#     tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)
#     assert taco_application.authorizedStake(staking_provider) == value
#     assert taco_application.stakingProviderToOperator(staking_provider) == operator
#     assert taco_application.operatorToStakingProvider(operator) == staking_provider

#     assert child_application.stakingProviderInfo(staking_provider) == (
#         value,
#         value // 3,
#     )
#     assert child_application.stakingProviderToOperator(staking_provider) == operator
#     assert child_application.operatorToStakingProvider(operator) == staking_provider


#     assert tx.events == [
#         taco_application.ManualChildSynchronizationSent(
#             stakingProvider=staking_provider,
#             authorized=value,
#             deauthorizing=value // 3,
#             endDeauthorization=0,
#             operator=operator,
#         )
#     ]
def test_add_stakeless_provider(accounts, taco_application, child_application, chain):
    """
    Tests for authorization method: addStakelessProvider
    """

    creator, staking_provider, owner = accounts[0:3]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Only owner can call `addStakelessProvider` directly
    with ape.reverts():
        taco_application.addStakelessProvider(
            staking_provider, staking_provider, sender=staking_provider
        )

    with ape.reverts("Parameters must be specified"):
        taco_application.addStakelessProvider(ZERO_ADDRESS, staking_provider, sender=creator)
    with ape.reverts("Parameters must be specified"):
        taco_application.addStakelessProvider(staking_provider, ZERO_ADDRESS, sender=creator)

    tx = taco_application.addStakelessProvider(staking_provider, owner, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (value, 0)
    assert taco_application.isAuthorized(staking_provider)

    # Check that all events are emitted
    events = [event for event in tx.events if event.event_name == "StakelessProvderAdded"]
    assert events == [taco_application.StakelessProvderAdded(stakingProvider=staking_provider)]

    with ape.reverts("Staker already exists"):
        taco_application.addStakelessProvider(staking_provider, staking_provider, sender=creator)

    taco_application.bondOperator(staking_provider, owner, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=owner)

    with ape.reverts("A provider can't be an operator for another provider"):
        taco_application.addStakelessProvider(owner, owner, sender=creator)
