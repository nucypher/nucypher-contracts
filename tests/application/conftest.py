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
from brownie import Wei

MIN_AUTHORIZATION = Wei("40_000 ether")
MIN_OPERATOR_SECONDS = 24 * 60 * 60

# @pytest.fixture()
# def token(deploy_contract, token_economics):
#     # Create an ERC20 token
#     token, _ = deploy_contract('TToken', _totalSupplyOfTokens=token_economics.erc20_total_supply)
#     return token


@pytest.fixture()
def threshold_staking(ThresholdStakingForPREApplicationMock, accounts):
    threshold_staking = accounts[0].deploy(ThresholdStakingForPREApplicationMock)
    return threshold_staking


@pytest.fixture()
def pre_application(SimplePREApplication, accounts, threshold_staking):
    contract = accounts[0].deploy(
        SimplePREApplication, threshold_staking.address, MIN_AUTHORIZATION, MIN_OPERATOR_SECONDS
    )

    threshold_staking.setApplication(contract.address)

    return contract
