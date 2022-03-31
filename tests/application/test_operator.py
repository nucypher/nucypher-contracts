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
import brownie
from brownie import Wei
from eth_utils import to_checksum_address

CONFIRMATION_SLOT = 1
MIN_AUTHORIZATION = Wei("40_000 ether")
MIN_OPERATOR_SECONDS = 24 * 60 * 60
NULL_ADDRESS = brownie.convert.to_address("0x" + "0" * 40)  # TODO move to some test constants


def test_bond_operator(accounts, threshold_staking, pre_application, chain):
    accounts.add()
    creator, staking_provider_1, staking_provider_2, staking_provider_3, staking_provider_4, \
    operator1, operator2, operator3, owner3, beneficiary, authorizer, *everyone_else = (
        accounts
    )
    min_authorization = MIN_AUTHORIZATION
    min_operator_seconds = MIN_OPERATOR_SECONDS

    # Prepare staking providers: two with intermediary contract and two just a staking provider
    threshold_staking.setRoles(staking_provider_1, {"from": creator})
    threshold_staking.setStakes(staking_provider_1, min_authorization, 0, 0, {"from": creator})
    threshold_staking.setRoles(staking_provider_2, {"from": creator})
    threshold_staking.setStakes(
        staking_provider_2,
        min_authorization // 3,
        min_authorization // 3,
        min_authorization // 3 - 1,
        {"from": creator},
    )
    threshold_staking.setRoles(
        staking_provider_3, owner3, beneficiary, authorizer, {"from": creator}
    )
    threshold_staking.setStakes(staking_provider_3, 0, min_authorization, 0, {"from": creator})
    threshold_staking.setRoles(staking_provider_4, {"from": creator})
    threshold_staking.setStakes(staking_provider_4, 0, 0, min_authorization, {"from": creator})

    assert pre_application.getOperatorFromStakingProvider(staking_provider_1) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(staking_provider_1) == NULL_ADDRESS
    assert pre_application.getOperatorFromStakingProvider(staking_provider_2) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(staking_provider_2) == NULL_ADDRESS
    assert pre_application.getOperatorFromStakingProvider(staking_provider_3) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(staking_provider_3) == NULL_ADDRESS
    assert pre_application.getOperatorFromStakingProvider(staking_provider_4) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(staking_provider_4) == NULL_ADDRESS

    # Staking provider can't confirm operator address because there is no operator by default
    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": staking_provider_1})

    # Staking provider can't bond another staking provider as operator
    with brownie.reverts():
        pre_application.bondOperator(
            staking_provider_1, staking_provider_2, {"from": staking_provider_1}
        )

    # Staking provider can't bond operator if stake is less than minimum
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_2, operator1, {"from": staking_provider_2})

    # Only staking provider or stake owner can bond operator
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_3, operator1, {"from": beneficiary})
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_3, operator1, {"from": authorizer})

    # Staking provider bonds operator and now operator can make a confirmation
    tx = pre_application.bondOperator(staking_provider_3, operator1, {"from": owner3})
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_3) == operator1
    assert pre_application.stakingProviderFromOperator(operator1) == staking_provider_3
    assert not pre_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not pre_application.isOperatorConfirmed(operator1)
    assert pre_application.getStakingProvidersLength() == 1
    assert pre_application.stakingProviders(0) == staking_provider_3

    # No active stakingProviders before confirmation
    all_locked, staking_providers = pre_application.getActiveStakingProviders(0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    pre_application.confirmOperatorAddress({"from": operator1})
    assert pre_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert pre_application.isOperatorConfirmed(operator1)

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_3
    assert event["operator"] == operator1
    assert event["startTimestamp"] == timestamp

    # After confirmation operator is becoming active
    all_locked, staking_providers = pre_application.getActiveStakingProviders(0, 0)
    assert all_locked == min_authorization
    assert len(staking_providers) == 1
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization

    # Operator is in use so other stakingProviders can't bond him
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_4, operator1, {"from": staking_provider_4})

    # # Operator can't be a staking provider
    # threshold_staking.setRoles(operator1, {"from": creator})
    # threshold_staking.setStakes(operator1, min_authorization, 0, 0, {"from": creator})
    # with brownie.reverts():
    #     threshold_staking.increaseAuthorization(
    #         operator1, min_authorization, pre_application.address, {'from': operator1})

    # Can't bond operator twice too soon
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_3, operator2, {"from": staking_provider_3})

    # She can't unbond her operator too, until enough time has passed
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_3, NULL_ADDRESS, {"from": staking_provider_3})

    # Let's advance some time and unbond the operator
    chain.sleep(min_operator_seconds)
    chain.mine()
    tx = pre_application.bondOperator(
        staking_provider_3, NULL_ADDRESS, {"from": staking_provider_3}
    )
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_3) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(staking_provider_3) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(operator1) == NULL_ADDRESS
    assert not pre_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not pre_application.isOperatorConfirmed(operator1)
    assert pre_application.getStakingProvidersLength() == 1
    assert pre_application.stakingProviders(0) == staking_provider_3

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = pre_application.getActiveStakingProviders(0, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_3
    # Now the operator has been unbonded ...
    assert event["operator"] == NULL_ADDRESS
    # ... with a new starting period.
    assert event["startTimestamp"] == timestamp

    # The staking provider can bond now a new operator, without waiting additional time.
    tx = pre_application.bondOperator(staking_provider_3, operator2, {"from": staking_provider_3})
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_3) == operator2
    assert pre_application.stakingProviderFromOperator(operator2) == staking_provider_3
    assert not pre_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]
    assert not pre_application.isOperatorConfirmed(operator2)
    assert pre_application.getStakingProvidersLength() == 1
    assert pre_application.stakingProviders(0) == staking_provider_3

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_3
    assert event["operator"] == operator2
    assert event["startTimestamp"] == timestamp

    # Now the previous operator can no longer make a confirmation
    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": operator1})
    # Only new operator can
    pre_application.confirmOperatorAddress({"from": operator2})
    assert not pre_application.isOperatorConfirmed(operator1)
    assert pre_application.isOperatorConfirmed(operator2)
    assert pre_application.stakingProviderInfo(staking_provider_3)[CONFIRMATION_SLOT]

    # Another staker can bond a free operator
    tx = pre_application.bondOperator(staking_provider_4, operator1, {"from": staking_provider_4})
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_4) == operator1
    assert pre_application.stakingProviderFromOperator(operator1) == staking_provider_4
    assert not pre_application.isOperatorConfirmed(operator1)
    assert not pre_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert pre_application.getStakingProvidersLength() == 2
    assert pre_application.stakingProviders(1) == staking_provider_4

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_4
    assert event["operator"] == operator1
    assert event["startTimestamp"] == timestamp

    # # The first operator still can't be a staking provider
    # threshold_staking.setRoles(operator1, {"from": creator})
    # threshold_staking.setStakes(operator1, min_authorization, 0, 0, {"from": creator})
    # with brownie.reverts():
    #     threshold_staking.increaseAuthorization(
    #         operator1, min_authorization, pre_application.address, {'from': operator1})

    # Bond operator again
    pre_application.confirmOperatorAddress({"from": operator1})
    assert pre_application.isOperatorConfirmed(operator1)
    assert pre_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    chain.sleep(min_operator_seconds)
    chain.mine()
    tx = pre_application.bondOperator(staking_provider_4, operator3, {"from": staking_provider_4})
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_4) == operator3
    assert pre_application.stakingProviderFromOperator(operator3) == staking_provider_4
    assert pre_application.stakingProviderFromOperator(operator1) == NULL_ADDRESS
    assert not pre_application.isOperatorConfirmed(operator3)
    assert not pre_application.isOperatorConfirmed(operator1)
    assert not pre_application.stakingProviderInfo(staking_provider_4)[CONFIRMATION_SLOT]
    assert pre_application.getStakingProvidersLength() == 2
    assert pre_application.stakingProviders(1) == staking_provider_4

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = pre_application.getActiveStakingProviders(1, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_4
    assert event["operator"] == operator3
    assert event["startTimestamp"] == timestamp

    # The first operator is free and can deposit tokens and become a staker
    threshold_staking.setRoles(operator1, {"from": creator})
    threshold_staking.setStakes(
        operator1,
        min_authorization // 3,
        min_authorization // 3,
        min_authorization // 3,
        {"from": creator},
    )
    # threshold_staking.increaseAuthorization(
    #     operator1, min_authorization, pre_application.address, {'from': operator1})
    assert pre_application.getOperatorFromStakingProvider(operator1) == NULL_ADDRESS
    assert pre_application.stakingProviderFromOperator(operator1) == NULL_ADDRESS

    chain.mine(timedelta=min_operator_seconds)

    # Staking provider can't bond the first operator again because operator is a provider now
    with brownie.reverts():
        pre_application.bondOperator(staking_provider_4, operator1, {"from": staking_provider_4})

    # Provider without intermediary contract can bond itself as operator
    # (Probably not best idea, but whatever)
    tx = pre_application.bondOperator(
        staking_provider_1, staking_provider_1, {"from": staking_provider_1}
    )
    timestamp = tx.timestamp
    assert pre_application.getOperatorFromStakingProvider(staking_provider_1) == staking_provider_1
    assert pre_application.stakingProviderFromOperator(staking_provider_1) == staking_provider_1
    assert pre_application.getStakingProvidersLength() == 3
    assert pre_application.stakingProviders(2) == staking_provider_1

    assert "OperatorBonded" in tx.events
    events = tx.events["OperatorBonded"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider_1
    assert event["operator"] == staking_provider_1
    assert event["startTimestamp"] == timestamp

    # If stake will be less than minimum then confirmation is not possible
    threshold_staking.setStakes(staking_provider_1, 0, min_authorization - 1, 0, {"from": creator})

    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": staking_provider_1})

    # Now provider can make a confirmation
    threshold_staking.setStakes(staking_provider_1, 0, 0, min_authorization, {"from": creator})
    pre_application.confirmOperatorAddress({"from": staking_provider_1})

    # If stake will be less than minimum then provider is not active
    all_locked, staking_providers = pre_application.getActiveStakingProviders(0, 0)
    assert all_locked == 2 * min_authorization
    assert len(staking_providers) == 2
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization
    assert to_checksum_address(staking_providers[1][0]) == staking_provider_1
    assert staking_providers[1][1] == min_authorization
    threshold_staking.setStakes(staking_provider_1, 0, min_authorization - 1, 0, {"from": creator})
    all_locked, staking_providers = pre_application.getActiveStakingProviders(1, 0)
    assert all_locked == 0
    assert len(staking_providers) == 0


def test_confirm_address(accounts, threshold_staking, pre_application, chain, Intermediary):
    creator, staking_provider, operator, *everyone_else = accounts
    min_authorization = MIN_AUTHORIZATION
    min_operator_seconds = MIN_OPERATOR_SECONDS

    # Operator must be associated with provider that has minimum amount of tokens
    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": staking_provider})
    threshold_staking.setRoles(staking_provider, {"from": creator})
    threshold_staking.setStakes(staking_provider, min_authorization - 1, 0, 0, {"from": creator})
    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": staking_provider})

    # Deploy intermediary contract
    intermediary = creator.deploy(Intermediary, pre_application.address)

    # Bond contract as an operator
    threshold_staking.setStakes(staking_provider, min_authorization, 0, 0, {"from": creator})
    pre_application.bondOperator(staking_provider, intermediary.address, {"from": staking_provider})

    # But can't make a confirmation using an intermediary contract
    with brownie.reverts():
        intermediary.confirmOperatorAddress({"from": staking_provider})

    # Bond operator again and make confirmation
    chain.mine(timedelta=min_operator_seconds)
    pre_application.bondOperator(staking_provider, operator, {"from": staking_provider})
    tx = pre_application.confirmOperatorAddress({"from": operator})
    assert pre_application.isOperatorConfirmed(operator)
    assert pre_application.stakingProviderInfo(staking_provider)[CONFIRMATION_SLOT]

    assert "OperatorConfirmed" in tx.events
    events = tx.events["OperatorConfirmed"]
    event = events[0]
    assert event["stakingProvider"] == staking_provider
    assert event["operator"] == operator

    # Can't confirm twice
    with brownie.reverts():
        pre_application.confirmOperatorAddress({"from": operator})
