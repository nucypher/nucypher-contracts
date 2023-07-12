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
from ape import project
from web3 import Web3


MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")

MIN_OPERATOR_SECONDS = 24 * 60 * 60

HASH_ALGORITHM_KECCAK256 = 0
HASH_ALGORITHM_SHA256 = 1
HASH_ALGORITHM_RIPEMD160 = 2
HASH_ALGORITHM = HASH_ALGORITHM_SHA256
BASE_PENALTY = 2
PENALTY_HISTORY_COEFFICIENT = 0
PERCENTAGE_PENALTY_COEFFICIENT = 100000
REWARD_DURATION = 60 * 60 * 24 * 7  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds
TOTAL_SUPPLY = Web3.to_wei(1_000_000_000, "ether")  # TODO NU(1_000_000_000, 'NU').to_units()

DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]


@pytest.fixture()
def token(project, accounts):
    # Create an ERC20 token
    token = accounts[0].deploy(project.TToken, TOTAL_SUPPLY)
    return token


@pytest.fixture()
def threshold_staking(project, accounts):
    threshold_staking = accounts[0].deploy(project.ThresholdStakingForPREApplicationMock)
    return threshold_staking


@pytest.fixture()
def pre_application(project, accounts, threshold_staking):
    contract = accounts[0].deploy(
        project.SimplePREApplication, threshold_staking.address, MIN_AUTHORIZATION, MIN_OPERATOR_SECONDS
    )

    threshold_staking.setApplication(contract.address, sender=accounts[0])

    return contract
