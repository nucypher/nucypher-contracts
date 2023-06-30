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
TOTAL_SUPPLY = Web3.to_wei(10_000_000_000, "ether")

HASH_ALGORITHM_KECCAK256 = 0
HASH_ALGORITHM_SHA256 = 1
HASH_ALGORITHM_RIPEMD160 = 2
HASH_ALGORITHM = HASH_ALGORITHM_SHA256
BASE_PENALTY = 2
PENALTY_HISTORY_COEFFICIENT = 0
PERCENTAGE_PENALTY_COEFFICIENT = 100000
REWARD_DURATION = 60 * 60 * 24 * 7  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds

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


def encode_function_data(initializer=None, *args):
    """Encodes the function call so we can work with an initializer.
    Args:
        initializer ([brownie.network.contract.ContractTx], optional):
        The initializer function we want to call. Example: `box.store`.
        Defaults to None.
        args (Any, optional):
        The arguments to pass to the initializer function
    Returns:
        [bytes]: Return the encoded bytes.
    """
    if not len(args):
        args = b""

    if initializer:
        return initializer.encode_input(*args)

    return b""


@pytest.fixture()
def pre_application(project, accounts, token, threshold_staking):
    creator = accounts[0]
    contract = creator.deploy(
        project.ExtendedPREApplication,
        token.address,
        threshold_staking.address,
        HASH_ALGORITHM,
        BASE_PENALTY,
        PENALTY_HISTORY_COEFFICIENT,
        PERCENTAGE_PENALTY_COEFFICIENT,
        MIN_AUTHORIZATION,
        MIN_OPERATOR_SECONDS,
        REWARD_DURATION,
        DEAUTHORIZATION_DURATION,
    )

    proxy_admin = DEPENDENCY.ProxyAdmin.deploy(sender=creator)
    encoded_initializer_function = encode_function_data()
    proxy = DEPENDENCY.TransparentUpgradeableProxy.deploy(
        contract.address,
        proxy_admin.address,
        encoded_initializer_function,
        sender=creator,
    )
    proxy_contract = project.ExtendedPREApplication.at(proxy.address)

    threshold_staking.setApplication(proxy_contract.address, sender=creator)
    proxy_contract.initialize(sender=creator)

    return proxy_contract
