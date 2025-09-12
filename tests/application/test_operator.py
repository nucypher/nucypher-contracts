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

CONFIRMATION_SLOT = 1
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")
MIN_OPERATOR_SECONDS = 24 * 60 * 60
PENALTY_DEFAULT = 1000  # 10% penalty
PENALTY_DURATION = 60 * 60 * 24  # 1 day in seconds
PENALTY_INCREMENT = 2500


def test_bond_operator(accounts, threshold_staking, taco_application, child_application, chain):
    (
        creator,
        staking_provider_1,
        staking_provider_2,
        staking_provider_3,
        staking_provider_4,
        operator1,
        operator2,
        operator3,
        owner3,
        beneficiary,
    ) = accounts[:10]
    authorizer = creator
    min_authorization = MIN_AUTHORIZATION
    min_operator_seconds = MIN_OPERATOR_SECONDS

    # Prepare staking providers
    threshold_staking.setRoles(staking_provider_1, sender=creator)
    threshold_staking.authorizationIncreased(
        staking_provider_1, 0, min_authorization, sender=creator
    )
    threshold_staking.setRoles(staking_provider_2, sender=creator)
    threshold_staking.setRoles(staking_provider_3, owner3, beneficiary, authorizer, sender=creator)
    threshold_staking.authorizationIncreased(
        staking_provider_3, 0, min_authorization, sender=creator
    )
    threshold_staking.setRoles(staking_provider_4, sender=creator)
    threshold_staking.authorizationIncreased(
        staking_provider_4, 0, min_authorization, sender=creator
    )

    assert taco_application.stakingProviderToOperator(staking_provider_1) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_1) == ZERO_ADDRESS
    assert taco_application.stakingProviderToOperator(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.stakingProviderToOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderToOperator(staking_provider_4) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_4) == ZERO_ADDRESS

    # Staking provider can't confirm operator address because there is no operator by default
    child_application.confirmOperatorAddress(staking_provider_1, sender=staking_provider_1)
    assert not taco_application.isOperatorConfirmed(staking_provider_1)

    # Staking provider can't bond another staking provider as operator
    with ape.reverts():
        taco_application.bondOperator(
            staking_provider_1, staking_provider_2, sender=staking_provider_1
        )

    # Staking provider can't bond operator if stake is less than minimum
    with ape.reverts():
        taco_application.bondOperator(staking_provider_2, operator1, sender=staking_provider_2)

    # Only staking provider or stake owner can bond operator
    with ape.reverts():
        taco_application.bondOperator(staking_provider_3, operator1, sender=beneficiary)
    with ape.reverts():
        taco_application.bondOperator(staking_provider_3, operator1, sender=authorizer)
    with ape.reverts():
        taco_application.registerOperator(operator1, sender=beneficiary)
    with ape.reverts():
        taco_application.registerOperator(operator1, sender=authorizer)

    # Staking provider bonds operator and now operator can make a confirmation
    tx = taco_application.bondOperator(staking_provider_3, operator1, sender=owner3)
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_3) == operator1
    assert taco_application.operatorToStakingProvider(operator1) == staking_provider_3
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator1)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.stakingProviderToOperator(staking_provider_3) == operator1
    assert child_application.operatorToStakingProvider(operator1) == staking_provider_3
    assert taco_application.authorizedOverall() == 0

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_3,
            operator=operator1,
            previousOperator=ZERO_ADDRESS,
            startTimestamp=timestamp,
        )
    ]

    # No active stakingProviders before confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    child_application.confirmOperatorAddress(operator1, sender=operator1)
    assert taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert taco_application.isOperatorConfirmed(operator1)
    assert child_application.stakingProviderToOperator(staking_provider_3) == operator1
    assert child_application.operatorToStakingProvider(operator1) == staking_provider_3

    # After confirmation operator is becoming active
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0, 0)
    assert all_locked == min_authorization
    assert len(staking_providers) == 1
    assert to_checksum_address(staking_providers[0][0:20]) == staking_provider_3
    assert to_int(staking_providers[0][20:32]) == min_authorization

    # Operator is in use so other stakingProviders can't bond him
    with ape.reverts():
        taco_application.bondOperator(staking_provider_4, operator1, sender=staking_provider_4)

    # Operator can't be a staking provider
    threshold_staking.setRoles(operator1, sender=creator)
    with ape.reverts():
        threshold_staking.authorizationIncreased(operator1, 0, min_authorization, sender=operator1)
    threshold_staking.setRoles(operator1, ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS, sender=creator)

    # Can't bond operator twice too soon
    with ape.reverts():
        taco_application.bondOperator(staking_provider_3, operator2, sender=staking_provider_3)

    # She can't unbond her operator too, until enough time has passed
    with ape.reverts():
        taco_application.bondOperator(staking_provider_3, ZERO_ADDRESS, sender=staking_provider_3)

    # Let's advance some time and unbond the operator
    chain.pending_timestamp += min_operator_seconds
    tx = taco_application.bondOperator(staking_provider_3, ZERO_ADDRESS, sender=staking_provider_3)
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator1) == ZERO_ADDRESS
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator1)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.stakingProviderToOperator(staking_provider_3) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator1) == ZERO_ADDRESS

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_3,
            operator=ZERO_ADDRESS,
            previousOperator=operator1,
            startTimestamp=timestamp,
        )
    ]

    # The staking provider can bond now a new operator, without waiting additional time.
    tx = taco_application.registerOperator(operator2, sender=staking_provider_3)
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_3) == operator2
    assert taco_application.operatorToStakingProvider(operator2) == staking_provider_3
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator2)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.stakingProviderToOperator(staking_provider_3) == operator2
    assert child_application.operatorToStakingProvider(operator2) == staking_provider_3

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_3,
            operator=operator2,
            previousOperator=ZERO_ADDRESS,
            startTimestamp=timestamp,
        )
    ]

    # Now the previous operator can no longer make a confirmation
    child_application.confirmOperatorAddress(operator1, sender=operator1)
    assert not taco_application.isOperatorConfirmed(operator1)
    # Only new operator can
    child_application.confirmOperatorAddress(operator2, sender=operator2)
    assert not taco_application.isOperatorConfirmed(operator1)
    assert taco_application.isOperatorConfirmed(operator2)
    assert taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert child_application.stakingProviderToOperator(staking_provider_3) == operator2
    assert child_application.operatorToStakingProvider(operator2) == staking_provider_3

    # Another staking provider can bond a free operator
    assert taco_application.authorizedOverall() == min_authorization
    tx = taco_application.bondOperator(staking_provider_4, operator1, sender=staking_provider_4)
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_4) == operator1
    assert taco_application.operatorToStakingProvider(operator1) == staking_provider_4
    assert not taco_application.isOperatorConfirmed(operator1)
    assert not taco_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert taco_application.getStakingProvidersLength() == 2
    assert taco_application.stakingProviders(1) == staking_provider_4
    assert taco_application.authorizedOverall() == min_authorization
    assert child_application.stakingProviderToOperator(staking_provider_4) == operator1
    assert child_application.operatorToStakingProvider(operator1) == staking_provider_4

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_4,
            operator=operator1,
            previousOperator=ZERO_ADDRESS,
            startTimestamp=timestamp,
        )
    ]

    # The first operator still can't be a staking provider
    threshold_staking.setRoles(operator1, sender=creator)
    with ape.reverts():
        threshold_staking.authorizationIncreased(operator1, 0, min_authorization, sender=operator1)
    threshold_staking.setRoles(operator1, ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS, sender=creator)

    # Bond operator again
    child_application.confirmOperatorAddress(operator1, sender=operator1)
    assert taco_application.isOperatorConfirmed(operator1)
    assert taco_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert taco_application.authorizedOverall() == 2 * min_authorization
    assert child_application.stakingProviderToOperator(staking_provider_4) == operator1
    assert child_application.operatorToStakingProvider(operator1) == staking_provider_4

    chain.pending_timestamp += min_operator_seconds
    tx = taco_application.bondOperator(staking_provider_4, operator3, sender=staking_provider_4)
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_4) == operator3
    assert taco_application.operatorToStakingProvider(operator3) == staking_provider_4
    assert taco_application.operatorToStakingProvider(operator1) == ZERO_ADDRESS
    assert not taco_application.isOperatorConfirmed(operator3)
    assert not taco_application.isOperatorConfirmed(operator1)
    assert not taco_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert taco_application.getStakingProvidersLength() == 2
    assert taco_application.stakingProviders(1) == staking_provider_4
    assert taco_application.authorizedOverall() == min_authorization
    assert child_application.stakingProviderToOperator(staking_provider_4) == operator3
    assert child_application.operatorToStakingProvider(operator1) == ZERO_ADDRESS
    assert child_application.operatorToStakingProvider(operator3) == staking_provider_4

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(1, 0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_4,
            operator=operator3,
            previousOperator=operator1,
            startTimestamp=timestamp,
        )
    ]

    # The first operator is free and can deposit tokens and become a staking provider
    threshold_staking.setRoles(operator1, sender=creator)
    threshold_staking.authorizationIncreased(operator1, 0, min_authorization, sender=operator1)
    assert taco_application.stakingProviderToOperator(operator1) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator1) == ZERO_ADDRESS

    chain.pending_timestamp += min_operator_seconds

    # Staking provider can't bond the first operator again because operator is a provider now
    with ape.reverts():
        taco_application.bondOperator(staking_provider_4, operator1, sender=staking_provider_4)

    # Provider without intermediary contract can bond itself as operator
    # (Probably not best idea, but whatever)
    tx = taco_application.bondOperator(
        staking_provider_1, staking_provider_1, sender=staking_provider_1
    )
    timestamp = tx.timestamp
    assert taco_application.stakingProviderToOperator(staking_provider_1) == staking_provider_1
    assert taco_application.operatorToStakingProvider(staking_provider_1) == staking_provider_1
    assert taco_application.getStakingProvidersLength() == 3
    assert taco_application.stakingProviders(2) == staking_provider_1

    events = [event for event in tx.events if event.event_name == "OperatorBonded"]
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_1,
            operator=staking_provider_1,
            previousOperator=ZERO_ADDRESS,
            startTimestamp=timestamp,
        )
    ]

    # If stake will be less than minimum then confirmation is still possible
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_1, min_authorization, min_authorization - 1, sender=creator
    )
    child_application.confirmOperatorAddress(staking_provider_1, sender=staking_provider_1)
    assert child_application.stakingProviderToOperator(staking_provider_1) == staking_provider_1
    assert child_application.operatorToStakingProvider(staking_provider_1) == staking_provider_1

    # If stake will be less than minimum then provider is not active
    threshold_staking.authorizationIncreased(
        staking_provider_1, min_authorization - 1, min_authorization, sender=creator
    )
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0, 0)
    assert all_locked == 2 * min_authorization
    assert len(staking_providers) == 2
    assert to_checksum_address(staking_providers[0][0:20]) == staking_provider_3
    assert to_int(staking_providers[0][20:32]) == min_authorization
    assert to_checksum_address(staking_providers[1][0:20]) == staking_provider_1
    assert to_int(staking_providers[1][20:32]) == min_authorization
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_1, min_authorization, min_authorization - 1, sender=creator
    )
    all_locked, staking_providers = taco_application.getActiveStakingProviders(1, 0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    # Unbond and rebond oeprator
    taco_application.registerOperator(ZERO_ADDRESS, sender=staking_provider_3)
    taco_application.registerOperator(operator2, sender=staking_provider_3)
    assert not taco_application.isOperatorConfirmed(operator2)

    # Operator can be unbonded before confirmation without restriction
    taco_application.bondOperator(staking_provider_3, ZERO_ADDRESS, sender=staking_provider_3)
    assert taco_application.stakingProviderToOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.operatorToStakingProvider(operator2) == ZERO_ADDRESS

    # Rebond operator by staker with penalty
    authorized_overall = taco_application.authorizedOverall()
    child_application.penalize(staking_provider_3, sender=staking_provider_2)
    taco_application.bondOperator(staking_provider_3, operator2, sender=owner3)
    assert taco_application.authorizedOverall() == authorized_overall

    # Confirm operator and rebond again
    chain.pending_timestamp += min_operator_seconds
    child_application.penalize(staking_provider_3, sender=staking_provider_2)
    child_application.confirmOperatorAddress(operator2, sender=operator2)
    assert taco_application.authorizedOverall() == authorized_overall + min_authorization * 9 // 10
    taco_application.bondOperator(staking_provider_3, staking_provider_3, sender=staking_provider_3)
    assert taco_application.authorizedOverall() == authorized_overall


def test_confirm_address(accounts, threshold_staking, taco_application, child_application, chain):
    creator, staking_provider, operator, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    min_operator_seconds = MIN_OPERATOR_SECONDS

    # Only child app can penalize
    with ape.reverts("Only child application allowed to confirm operator"):
        taco_application.confirmOperatorAddress(staking_provider, sender=staking_provider)

    # Skips confirmation if operator is not associated with staking provider
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    assert not taco_application.isOperatorConfirmed(staking_provider)

    threshold_staking.setRoles(staking_provider, sender=creator)
    threshold_staking.authorizationIncreased(staking_provider, 0, min_authorization, sender=creator)

    # Bond operator and make confirmation
    chain.pending_timestamp += min_operator_seconds
    taco_application.bondOperator(staking_provider, operator, sender=staking_provider)
    assert taco_application.authorizedOverall() == 0
    tx = child_application.confirmOperatorAddress(operator, sender=operator)
    assert taco_application.isOperatorConfirmed(operator)
    assert taco_application.stakingProviderInfo(staking_provider)[CONFIRMATION_SLOT]
    assert taco_application.authorizedOverall() == min_authorization

    events = [event for event in tx.events if event.event_name == "OperatorConfirmed"]
    assert events == [
        taco_application.OperatorConfirmed(stakingProvider=staking_provider, operator=operator)
    ]

    # Can confirm twice
    earned = taco_application.availableRewards(staking_provider)
    child_application.confirmOperatorAddress(operator, sender=operator)
    assert taco_application.isOperatorConfirmed(operator)
    assert taco_application.stakingProviderInfo(staking_provider)[CONFIRMATION_SLOT]
    assert taco_application.authorizedOverall() == min_authorization
    assert taco_application.availableRewards(staking_provider) == earned

    # Confirm again for staker with penalty
    child_application.penalize(staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == min_authorization * 9 // 10
    child_application.confirmOperatorAddress(operator, sender=operator)
    assert taco_application.authorizedOverall() == min_authorization * 9 // 10

    # Rebond and confirm again
    chain.pending_timestamp += min_operator_seconds
    child_application.penalize(staking_provider, sender=staking_provider)
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == 0
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == min_authorization * 9 // 10


def test_slash(accounts, threshold_staking, taco_application):
    creator, staking_provider, investigator, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    penalty = min_authorization

    taco_application.setAdjudicator(creator, sender=creator)
    taco_application.slash(staking_provider, penalty, investigator, sender=creator)
    assert threshold_staking.amountToSeize() == penalty
    assert threshold_staking.rewardMultiplier() == 100
    assert threshold_staking.notifier() == investigator
    assert threshold_staking.stakingProvidersToSeize(0) == staking_provider
    assert threshold_staking.getLengthOfStakingProvidersToSeize() == 1


def test_penalize(accounts, threshold_staking, taco_application, child_application, chain):
    creator, staking_provider, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION

    # Only child app can penalize
    with ape.reverts("Only child application allowed to penalize"):
        taco_application.penalize(staking_provider, sender=creator)

    # Skips penalty if staking provider was not specified
    child_application.penalize(ZERO_ADDRESS, sender=staking_provider)
    assert taco_application.getPenalty(staking_provider) == [0, 0]

    # Penalize staking provider with 0 authorization
    tx = child_application.penalize(staking_provider, sender=staking_provider)
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    assert taco_application.getPenalty(staking_provider) == [PENALTY_DEFAULT, end_of_penalty]
    assert tx.events == [
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=PENALTY_DEFAULT,
            endPenalty=end_of_penalty,
        )
    ]
    assert taco_application.authorizedOverall() == 0

    # Increase authorization with no confirmation and check penalty
    chain.pending_timestamp += PENALTY_DURATION
    threshold_staking.authorizationIncreased(staking_provider, 0, min_authorization, sender=creator)
    tx = child_application.penalize(staking_provider, sender=staking_provider)
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    assert taco_application.getPenalty(staking_provider) == [PENALTY_DEFAULT, end_of_penalty]
    assert taco_application.authorizedOverall() == 0
    assert tx.events == [
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=PENALTY_DEFAULT,
            endPenalty=end_of_penalty,
        )
    ]

    # Increase authorization with confirmation and check penalty
    chain.pending_timestamp += PENALTY_DURATION
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    assert taco_application.authorizedOverall() == min_authorization
    tx = child_application.penalize(staking_provider, sender=staking_provider)
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    assert taco_application.getPenalty(staking_provider) == [PENALTY_DEFAULT, end_of_penalty]
    assert taco_application.authorizedOverall() == min_authorization * 9 / 10
    assert tx.events == [
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=PENALTY_DEFAULT,
            endPenalty=end_of_penalty,
        )
    ]

    # Penalize again
    tx = child_application.penalize(staking_provider, sender=staking_provider)
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    assert taco_application.getPenalty(staking_provider) == [
        PENALTY_DEFAULT + PENALTY_INCREMENT,
        end_of_penalty,
    ]
    assert taco_application.authorizedOverall() == min_authorization * 65 / 100  # 65%
    assert tx.events == [
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=PENALTY_DEFAULT + PENALTY_INCREMENT,
            endPenalty=end_of_penalty,
        )
    ]

    # Penalize several times in a row
    chain.pending_timestamp += PENALTY_DURATION
    child_application.penalize(staking_provider, sender=staking_provider)  # 90%
    child_application.penalize(staking_provider, sender=staking_provider)  # 65%
    child_application.penalize(staking_provider, sender=staking_provider)  # 40%
    child_application.penalize(staking_provider, sender=staking_provider)  # 15%
    tx = child_application.penalize(staking_provider, sender=staking_provider)  # 0%
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    penalty_base = taco_application.PENALTY_BASE()
    assert taco_application.getPenalty(staking_provider) == [penalty_base, end_of_penalty]
    assert taco_application.authorizedOverall() == 0
    assert tx.events == [
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=penalty_base,
            endPenalty=end_of_penalty,
        )
    ]

    # Penalize again after first penalty is over
    chain.pending_timestamp += PENALTY_DURATION
    tx = child_application.penalize(staking_provider, sender=staking_provider)
    timestamp = tx.timestamp
    end_of_penalty = timestamp + PENALTY_DURATION
    assert taco_application.getPenalty(staking_provider) == [PENALTY_DEFAULT, end_of_penalty]
    assert taco_application.authorizedOverall() == min_authorization * 9 / 10
    assert tx.events == [
        taco_application.RewardReset(stakingProvider=staking_provider),
        taco_application.Penalized(
            stakingProvider=staking_provider,
            penaltyPercent=PENALTY_DEFAULT,
            endPenalty=end_of_penalty,
        ),
    ]


def test_reset_reward(accounts, threshold_staking, taco_application, child_application, chain):
    creator, staking_provider, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION

    # This method only for penalized staking providers
    with ape.reverts("There is no penalty"):
        taco_application.resetReward(staking_provider, sender=creator)

    # Penalize staking provider
    child_application.penalize(staking_provider, sender=staking_provider)

    # Not enough time passed
    with ape.reverts("Penalty is still ongoing"):
        taco_application.resetReward(staking_provider, sender=creator)

    chain.pending_timestamp += PENALTY_DURATION
    tx = taco_application.resetReward(staking_provider, sender=creator)
    assert taco_application.getPenalty(staking_provider) == [0, 0]
    assert taco_application.authorizedOverall() == 0
    assert tx.events == [taco_application.RewardReset(stakingProvider=staking_provider)]

    # Increase authorization with no confirmation and reset reward
    threshold_staking.authorizationIncreased(staking_provider, 0, min_authorization, sender=creator)
    child_application.penalize(staking_provider, sender=staking_provider)
    chain.pending_timestamp += PENALTY_DURATION
    tx = taco_application.resetReward(staking_provider, sender=creator)
    assert taco_application.getPenalty(staking_provider) == [0, 0]
    assert taco_application.authorizedOverall() == 0
    assert tx.events == [taco_application.RewardReset(stakingProvider=staking_provider)]

    # Increase authorization with confirmation and reset reward
    taco_application.bondOperator(staking_provider, staking_provider, sender=staking_provider)
    child_application.confirmOperatorAddress(staking_provider, sender=staking_provider)
    child_application.penalize(staking_provider, sender=staking_provider)
    chain.pending_timestamp += PENALTY_DURATION
    assert taco_application.authorizedOverall() == min_authorization * 9 / 10
    tx = taco_application.resetReward(staking_provider, sender=creator)
    assert taco_application.getPenalty(staking_provider) == [0, 0]
    assert taco_application.authorizedOverall() == min_authorization
    assert tx.events == [taco_application.RewardReset(stakingProvider=staking_provider)]


def test_release(accounts, threshold_staking, taco_application, child_application, chain):
    creator, staking_provider, *everyone_else = accounts[0:]

    # Only child app can penalize
    with ape.reverts("Only child application allowed to release"):
        taco_application.release(staking_provider, sender=creator)

    # Release staking provider
    assert not taco_application.stakingProviderReleased(staking_provider)
    tx = child_application.release(staking_provider, sender=staking_provider)
    assert tx.events == [
        taco_application.Released(
            stakingProvider=staking_provider,
        )
    ]
    assert taco_application.stakingProviderReleased(staking_provider)
