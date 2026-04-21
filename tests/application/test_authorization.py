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

    with ape.reverts("Parameters are empty"):
        taco_application.initializeStake(staking_provider, owner, ZERO_ADDRESS, sender=creator)
    with ape.reverts("Parameters are empty"):
        taco_application.initializeStake(
            staking_provider, ZERO_ADDRESS, beneficiary, sender=creator
        )
    with ape.reverts("Parameters are empty"):
        taco_application.initializeStake(ZERO_ADDRESS, owner, beneficiary, sender=creator)

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

    child_application.setRelease(True, sender=creator)
    taco_application.requestUnstake(staking_provider, sender=staking_provider)
    with ape.reverts("Stake already initialized"):
        taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)


def test_request_unstake_callers(accounts, taco_application, token, child_application):
    """
    Tests for authorization method: requestUnstake
    """

    creator, staking_provider, owner, beneficiary, staking_provider_2, staking_provider_3 = accounts[0:6]
    value = MIN_AUTHORIZATION

    # Prepare staking providers
    token.transfer(owner, value, sender=creator)
    token.approve(taco_application.address, value, sender=owner)
    taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)

    token.transfer(staking_provider_2, value, sender=creator)
    token.approve(taco_application.address, value, sender=staking_provider_2)
    taco_application.initializeStake(
        staking_provider_2, staking_provider_2, staking_provider_2, sender=creator
    )

    token.transfer(staking_provider_3, value, sender=creator)
    token.approve(taco_application.address, value, sender=staking_provider_3)
    taco_application.initializeStake(
        staking_provider_3, staking_provider_3, staking_provider_3, sender=creator
    )

    assert taco_application.eligibleStake(staking_provider) == value
    assert taco_application.eligibleStake(staking_provider_2) == value
    assert taco_application.eligibleStake(staking_provider_3) == value

    # Only staking provider, stake owner or contract owner can call
    with ape.reverts("Not owner or provider"):
        taco_application.requestUnstake(staking_provider, sender=beneficiary)

    with ape.reverts("Not owner or provider"):
        taco_application.requestUnstake(staking_provider_2, sender=staking_provider_3)

    # For the first staking provider, let's check that the stake owner can call
    taco_application.requestUnstake(staking_provider, sender=owner)
    assert taco_application.eligibleStake(staking_provider) == 0

    # For the second staking provider, let's check that the staking provider can call
    taco_application.requestUnstake(staking_provider_2, sender=staking_provider_2)
    assert taco_application.eligibleStake(staking_provider_2) == 0

    # For the third staking provider, let's check that the contract owner can call
    taco_application.requestUnstake(staking_provider_3, sender=creator)
    assert taco_application.eligibleStake(staking_provider_3) == 0


def test_request_unstake(accounts, taco_application, child_application, token):
    """
    Tests for authorization method: requestUnstake
    """

    creator, staking_provider, owner, beneficiary, staking_provider_2 = accounts[0:5]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Prepare staking providers
    token.transfer(owner, value, sender=creator)
    token.approve(taco_application.address, value, sender=owner)
    taco_application.initializeStake(staking_provider, owner, beneficiary, sender=creator)

    # Request of unstaking
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    tx = taco_application.requestUnstake(staking_provider, sender=staking_provider)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == value
    assert taco_application.authorizedStake(staking_provider) == value
    assert child_application.stakingProviderInfo(staking_provider) == (
        value,
        value,
    )
    assert taco_application.isAuthorized(staking_provider)
    assert taco_application.eligibleStake(staking_provider) == 0

    events = [event for event in tx.events if event.event_name == "UnstakeRequested"]
    assert events == [taco_application.UnstakeRequested(stakingProvider=staking_provider)]

    assert child_application.stakingProviderReleased(staking_provider)

    with ape.reverts("Unstake already requested"):
        taco_application.requestUnstake(staking_provider, sender=staking_provider)

    # Confirm operator address and request full decrease
    token.transfer(staking_provider_2, value, sender=creator)
    token.approve(taco_application.address, value, sender=staking_provider_2)
    taco_application.initializeStake(
        staking_provider_2, staking_provider_2, staking_provider_2, sender=creator
    )

    taco_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)
    child_application.confirmOperatorAddress(staking_provider_2, sender=staking_provider_2)
    child_application.setRelease(True, sender=creator)

    tx = taco_application.requestUnstake(staking_provider_2, sender=staking_provider_2)
    assert taco_application.stakingProviderInfo(staking_provider_2)[AUTHORIZATION_SLOT] == 0
    assert taco_application.authorizedStake(staking_provider_2) == 0
    assert child_application.stakingProviderInfo(staking_provider_2) == (
        0,
        0,
    )
    assert not taco_application.isAuthorized(staking_provider_2)
    assert taco_application.eligibleStake(staking_provider_2) == 0

    events = [event for event in tx.events if event.event_name == "UnstakeRequested"]
    assert events == [taco_application.UnstakeRequested(stakingProvider=staking_provider_2)]

    assert child_application.stakingProviderReleased(staking_provider_2)


def test_release(accounts, token, taco_application, child_application):
    """
    Tests for authorization method: release+approveUnstake
    """

    creator, staking_provider, owner, staking_provider_2, staking_provider_3 = accounts[0:5]
    minimum_authorization = MIN_AUTHORIZATION
    value = minimum_authorization

    # Prepare staking providers
    token.transfer(owner, value, sender=creator)
    token.approve(taco_application.address, value, sender=owner)
    taco_application.initializeStake(staking_provider, owner, staking_provider, sender=creator)

    # Can't call directly
    with ape.reverts("Only child application allowed to release"):
        taco_application.release(staking_provider, sender=creator)

    # Can't approve decrease without request
    child_application.setRelease(True, sender=creator)
    with ape.reverts("There is no unstaking in process"):
        child_application.release(staking_provider, sender=creator)

    child_application.setRelease(False, sender=creator)
    taco_application.requestUnstake(staking_provider, sender=staking_provider)
    assert token.balanceOf(taco_application.address) == value
    assert token.balanceOf(owner) == 0

    child_application.setRelease(True, sender=creator)
    tx = child_application.release(staking_provider, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider)[AUTHORIZATION_SLOT] == 0
    assert not taco_application.isAuthorized(staking_provider)

    events = [event for event in tx.events if event.event_name == "UnstakeApproved"]
    assert events == [taco_application.UnstakeApproved(stakingProvider=staking_provider)]
    assert token.balanceOf(taco_application.address) == 0
    assert token.balanceOf(owner) == value

    # Bond operator and request decrease again
    token.transfer(staking_provider_2, value, sender=creator)
    token.approve(taco_application.address, value, sender=staking_provider_2)
    taco_application.initializeStake(
        staking_provider_2, staking_provider_2, staking_provider_2, sender=creator
    )
    taco_application.bondOperator(staking_provider_2, staking_provider_2, sender=staking_provider_2)

    child_application.setRelease(False, sender=creator)
    taco_application.requestUnstake(staking_provider_2, sender=staking_provider_2)
    assert token.balanceOf(taco_application.address) == value
    assert token.balanceOf(staking_provider_2) == 0

    child_application.setRelease(True, sender=creator)
    tx = child_application.release(staking_provider_2, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider_2)[AUTHORIZATION_SLOT] == 0
    assert taco_application.stakingProviderToOperator(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_2) == ZERO_ADDRESS
    assert child_application.stakingProviderInfo(staking_provider_2) == (0, 0)
    assert not taco_application.isAuthorized(staking_provider_2)
    assert not taco_application.isOperatorConfirmed(staking_provider_2)

    events = [event for event in tx.events if event.event_name == "UnstakeApproved"]
    assert events == [taco_application.UnstakeApproved(stakingProvider=staking_provider_2)]
    assert token.balanceOf(taco_application.address) == 0
    assert token.balanceOf(staking_provider_2) == value

    # Release stakeless node
    taco_application.addStakelessProvider(staking_provider_3, staking_provider_3, sender=creator)

    child_application.setRelease(False, sender=creator)
    taco_application.requestUnstake(staking_provider_3, sender=staking_provider_3)
    assert token.balanceOf(taco_application.address) == 0
    assert token.balanceOf(staking_provider_3) == 0

    child_application.setRelease(True, sender=creator)
    tx = child_application.release(staking_provider_3, sender=creator)
    assert taco_application.stakingProviderInfo(staking_provider_3)[AUTHORIZATION_SLOT] == 0
    assert taco_application.stakingProviderToOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert child_application.stakingProviderInfo(staking_provider_3) == (0, 0)
    assert not taco_application.isAuthorized(staking_provider_3)
    assert not taco_application.isOperatorConfirmed(staking_provider_3)

    events = [event for event in tx.events if event.event_name == "UnstakeApproved"]
    assert events == [taco_application.UnstakeApproved(stakingProvider=staking_provider_3)]
    assert token.balanceOf(taco_application.address) == 0
    assert token.balanceOf(staking_provider_3) == 0


def test_child_sync(accounts, taco_application, child_application, token, chain):
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
    token.transfer(staking_provider, value, sender=creator)
    token.approve(taco_application.address, value, sender=staking_provider)
    taco_application.initializeStake(
        staking_provider, staking_provider, staking_provider, sender=creator
    )
    taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
    child_application.updateAuthorization(staking_provider, 0, 0, 0, sender=creator)
    child_application.updateOperator(staking_provider, ZERO_ADDRESS, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == minimum_authorization
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (0, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator) == ZERO_ADDRESS

    # Manual sync state with child
    tx = taco_application.manualChildSynchronization(staking_provider, sender=creator)

    assert taco_application.authorizedStake(staking_provider) == minimum_authorization
    assert taco_application.stakingProviderToOperator(staking_provider) == operator
    assert taco_application.operatorToStakingProvider(operator) == staking_provider

    assert child_application.stakingProviderInfo(staking_provider) == (minimum_authorization, 0)
    assert child_application.stakingProviderToOperator(staking_provider) == operator
    assert child_application.operatorToStakingProvider(operator) == staking_provider

    assert tx.events == [
        taco_application.ManualChildSynchronizationSent(
            stakingProvider=staking_provider,
            authorized=minimum_authorization,
            deauthorizing=0,
            endDeauthorization=0,
            operator=operator,
        )
    ]


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
    events = [event for event in tx.events if event.event_name == "StakelessProviderAdded"]
    assert events == [taco_application.StakelessProviderAdded(stakingProvider=staking_provider)]

    with ape.reverts("Staker already exists"):
        taco_application.addStakelessProvider(staking_provider, staking_provider, sender=creator)

    taco_application.bondOperator(staking_provider, owner, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=owner)

    with ape.reverts("A provider can't be an operator for another provider"):
        taco_application.addStakelessProvider(owner, owner, sender=creator)
