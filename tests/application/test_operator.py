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
from eth_utils import to_checksum_address
from web3 import Web3

CONFIRMATION_SLOT = 1
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")
MIN_OPERATOR_SECONDS = 24 * 60 * 60


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

    assert taco_application.getOperatorFromStakingProvider(staking_provider_1) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_1) == ZERO_ADDRESS
    assert taco_application.getOperatorFromStakingProvider(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_2) == ZERO_ADDRESS
    assert taco_application.getOperatorFromStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.getOperatorFromStakingProvider(staking_provider_4) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_4) == ZERO_ADDRESS

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

    # Staking provider bonds operator and now operator can make a confirmation
    tx = taco_application.bondOperator(staking_provider_3, operator1, sender=owner3)
    timestamp = tx.timestamp
    assert taco_application.getOperatorFromStakingProvider(staking_provider_3) == operator1
    assert taco_application.stakingProviderFromOperator(operator1) == staking_provider_3
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator1)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.operatorFromStakingProvider(staking_provider_3) == operator1
    assert child_application.stakingProviderFromOperator(operator1) == staking_provider_3

    # No active stakingProviders before confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    child_application.confirmOperatorAddress(operator1, sender=operator1)
    assert taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert taco_application.isOperatorConfirmed(operator1)
    assert child_application.operatorFromStakingProvider(staking_provider_3) == operator1
    assert child_application.stakingProviderFromOperator(operator1) == staking_provider_3

    events = taco_application.OperatorBonded.from_receipt(tx)
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_3,
            operator=operator1,
            previousOperator=ZERO_ADDRESS,
            startTimestamp=timestamp,
        )
    ]

    # After confirmation operator is becoming active
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0)
    assert all_locked == min_authorization
    assert len(staking_providers) == 1
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization

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
    assert taco_application.getOperatorFromStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(operator1) == ZERO_ADDRESS
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator1)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.operatorFromStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert child_application.stakingProviderFromOperator(operator1) == ZERO_ADDRESS

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    events = taco_application.OperatorBonded.from_receipt(tx)
    assert events == [
        taco_application.OperatorBonded(
            stakingProvider=staking_provider_3,
            operator=ZERO_ADDRESS,
            previousOperator=operator1,
            startTimestamp=timestamp,
        )
    ]

    # The staking provider can bond now a new operator, without waiting additional time.
    tx = taco_application.bondOperator(staking_provider_3, operator2, sender=staking_provider_3)
    timestamp = tx.timestamp
    assert taco_application.getOperatorFromStakingProvider(staking_provider_3) == operator2
    assert taco_application.stakingProviderFromOperator(operator2) == staking_provider_3
    assert not taco_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not taco_application.isOperatorConfirmed(operator2)
    assert taco_application.getStakingProvidersLength() == 1
    assert taco_application.stakingProviders(0) == staking_provider_3
    assert child_application.operatorFromStakingProvider(staking_provider_3) == operator2
    assert child_application.stakingProviderFromOperator(operator2) == staking_provider_3

    events = taco_application.OperatorBonded.from_receipt(tx)
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
    assert child_application.operatorFromStakingProvider(staking_provider_3) == operator2
    assert child_application.stakingProviderFromOperator(operator2) == staking_provider_3

    # Another staking provider can bond a free operator
    assert taco_application.authorizedOverall() == min_authorization
    tx = taco_application.bondOperator(staking_provider_4, operator1, sender=staking_provider_4)
    timestamp = tx.timestamp
    assert taco_application.getOperatorFromStakingProvider(staking_provider_4) == operator1
    assert taco_application.stakingProviderFromOperator(operator1) == staking_provider_4
    assert not taco_application.isOperatorConfirmed(operator1)
    assert not taco_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert taco_application.getStakingProvidersLength() == 2
    assert taco_application.stakingProviders(1) == staking_provider_4
    assert taco_application.authorizedOverall() == min_authorization
    assert child_application.operatorFromStakingProvider(staking_provider_4) == operator1
    assert child_application.stakingProviderFromOperator(operator1) == staking_provider_4

    events = taco_application.OperatorBonded.from_receipt(tx)
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
    assert child_application.operatorFromStakingProvider(staking_provider_4) == operator1
    assert child_application.stakingProviderFromOperator(operator1) == staking_provider_4

    chain.pending_timestamp += min_operator_seconds
    tx = taco_application.bondOperator(staking_provider_4, operator3, sender=staking_provider_4)
    timestamp = tx.timestamp
    assert taco_application.getOperatorFromStakingProvider(staking_provider_4) == operator3
    assert taco_application.stakingProviderFromOperator(operator3) == staking_provider_4
    assert taco_application.stakingProviderFromOperator(operator1) == ZERO_ADDRESS
    assert not taco_application.isOperatorConfirmed(operator3)
    assert not taco_application.isOperatorConfirmed(operator1)
    assert not taco_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert taco_application.getStakingProvidersLength() == 2
    assert taco_application.stakingProviders(1) == staking_provider_4
    assert taco_application.authorizedOverall() == min_authorization
    assert child_application.operatorFromStakingProvider(staking_provider_4) == operator3
    assert child_application.stakingProviderFromOperator(operator1) == ZERO_ADDRESS
    assert child_application.stakingProviderFromOperator(operator3) == staking_provider_4

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = taco_application.getActiveStakingProviders(1, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    events = taco_application.OperatorBonded.from_receipt(tx)
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
    assert taco_application.getOperatorFromStakingProvider(operator1) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(operator1) == ZERO_ADDRESS

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
    assert taco_application.getOperatorFromStakingProvider(staking_provider_1) == staking_provider_1
    assert taco_application.stakingProviderFromOperator(staking_provider_1) == staking_provider_1
    assert taco_application.getStakingProvidersLength() == 3
    assert taco_application.stakingProviders(2) == staking_provider_1

    events = taco_application.OperatorBonded.from_receipt(tx)
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
    assert child_application.operatorFromStakingProvider(staking_provider_1) == staking_provider_1
    assert child_application.stakingProviderFromOperator(staking_provider_1) == staking_provider_1

    # If stake will be less than minimum then provider is not active
    threshold_staking.authorizationIncreased(
        staking_provider_1, min_authorization - 1, min_authorization, sender=creator
    )
    all_locked, staking_providers = taco_application.getActiveStakingProviders(0, 0)
    assert all_locked == 2 * min_authorization
    assert len(staking_providers) == 2
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization
    assert to_checksum_address(staking_providers[1][0]) == staking_provider_1
    assert staking_providers[1][1] == min_authorization
    threshold_staking.involuntaryAuthorizationDecrease(
        staking_provider_1, min_authorization, min_authorization - 1, sender=creator
    )
    all_locked, staking_providers = taco_application.getActiveStakingProviders(1, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    # Reset xchain contract before next bonding
    taco_application.setChildApplication(ZERO_ADDRESS, sender=creator)

    # Unbond and rebond oeprator
    taco_application.bondOperator(staking_provider_3, ZERO_ADDRESS, sender=staking_provider_3)
    taco_application.bondOperator(staking_provider_3, operator2, sender=staking_provider_3)
    assert not taco_application.isOperatorConfirmed(operator2)

    # Operator can be unbonded before confirmation without restriction
    taco_application.bondOperator(staking_provider_3, ZERO_ADDRESS, sender=staking_provider_3)
    assert taco_application.getOperatorFromStakingProvider(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(staking_provider_3) == ZERO_ADDRESS
    assert taco_application.stakingProviderFromOperator(operator2) == ZERO_ADDRESS


def test_confirm_address(
    accounts, threshold_staking, taco_application, child_application, chain, project
):
    creator, staking_provider, operator, *everyone_else = accounts[0:]
    min_authorization = MIN_AUTHORIZATION
    min_operator_seconds = MIN_OPERATOR_SECONDS

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

    events = taco_application.OperatorConfirmed.from_receipt(tx)
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
