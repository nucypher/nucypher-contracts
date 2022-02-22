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

import pytest
from brownie import Contract, Wei

TOTAL_SUPPLY = Wei("1_000_000_000 ether")  # TODO NU(1_000_000_000, 'NU').to_units()


@pytest.fixture()
def token(NuCypherToken, accounts):
    # Create an ERC20 token
    token = accounts[0].deploy(NuCypherToken, TOTAL_SUPPLY)
    return token


@pytest.fixture()
def worklock(WorkLockForStakingEscrowMock, token, accounts):
    worklock = accounts[0].deploy(WorkLockForStakingEscrowMock, token.address)
    return worklock


@pytest.fixture()
def threshold_staking(ThresholdStakingForStakingEscrowMock, accounts):
    threshold_staking = accounts[0].deploy(ThresholdStakingForStakingEscrowMock)
    return threshold_staking


@pytest.fixture(params=[False, True])
def escrow(
    Dispatcher, EnhancedStakingEscrow, token, worklock, threshold_staking, request, accounts
):
    contract = accounts[0].deploy(
        EnhancedStakingEscrow, token.address, worklock.address, threshold_staking.address
    )

    if request.param:
        dispatcher = accounts[0].deploy(Dispatcher, contract.address)
        contract = Contract.from_abi(
            name="EnhancedStakingEscrow", abi=contract.abi, address=dispatcher.address
        )

    worklock.setStakingEscrow(contract.address)
    threshold_staking.setStakingEscrow(contract.address)

    assert contract.token() == token.address
    assert contract.workLock() == worklock.address

    return contract
