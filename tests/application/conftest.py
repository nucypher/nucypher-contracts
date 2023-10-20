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
from web3 import Web3

MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")

MIN_OPERATOR_SECONDS = 24 * 60 * 60
TOTAL_SUPPLY = Web3.to_wei(10_000_000_000, "ether")

REWARD_DURATION = 60 * 60 * 24 * 7  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds
TOTAL_SUPPLY = Web3.to_wei(1_000_000_000, "ether")  # TODO NU(1_000_000_000, 'NU').to_units()
COMMITMENT_DURATION_1 = 182 * 60 * 24 * 60  # 182 days in seconds
COMMITMENT_DURATION_2 = 2 * COMMITMENT_DURATION_1  # 365 days in seconds
COMMITMENT_DURATION_3 = 3 * COMMITMENT_DURATION_1  # 365 days in seconds


@pytest.fixture()
def token(project, accounts):
    # Create an ERC20 token
    token = accounts[0].deploy(project.TToken, TOTAL_SUPPLY)
    return token


@pytest.fixture()
def threshold_staking(project, accounts):
    threshold_staking = accounts[0].deploy(project.ThresholdStakingForTACoApplicationMock)
    return threshold_staking


def encode_function_data(initializer=None, *args):
    """Encodes the function call so we can work with an initializer.
    Args:
        initializer ([ape.Contract.ContractMethodHandler], optional):
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
def taco_application(project, creator, token, threshold_staking, oz_dependency):
    contract = creator.deploy(
        project.TACoApplication,
        token.address,
        threshold_staking.address,
        MIN_AUTHORIZATION,
        MIN_OPERATOR_SECONDS,
        REWARD_DURATION,
        DEAUTHORIZATION_DURATION,
        [COMMITMENT_DURATION_1, COMMITMENT_DURATION_2, COMMITMENT_DURATION_3],
    )

    proxy_admin = oz_dependency.ProxyAdmin.deploy(creator, sender=creator)
    encoded_initializer_function = encode_function_data()
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        proxy_admin.address,
        encoded_initializer_function,
        sender=creator,
    )
    proxy_contract = project.TACoApplication.at(proxy.address)

    threshold_staking.setApplication(proxy_contract.address, sender=creator)
    proxy_contract.initialize(sender=creator)

    return proxy_contract


@pytest.fixture()
def child_application(project, creator, taco_application):
    contract = project.ChildApplicationForTACoApplicationMock.deploy(
        taco_application.address, sender=creator
    )
    taco_application.setChildApplication(contract.address, sender=creator)
    return contract
