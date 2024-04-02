#!/usr/bin/python3


from ape import networks, project

from deployment.constants import ARTIFACTS_DIR, LYNX_NODES
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"


def configure_sepolia_root(transactor: Transactor) -> int:
    """Configures ThresholdStaking and TACoApplication on Sepolia."""
    # Set up lynx stakes on Sepolia
    eth_network = networks.ethereum.sepolia
    with eth_network.use_provider("infura"):
        deployments = contracts_from_registry(
            filepath=LYNX_REGISTRY_FILEPATH, chain_id=eth_network.chain_id
        )

        taco_application_contract = deployments[project.TACoApplication.contract_type.name]
        threshold_staking_contract = deployments[project.TestnetThresholdStaking.contract_type.name]

        min_stake_size = taco_application_contract.minimumAuthorization()
        for staking_provider, operator in LYNX_NODES.items():
            # staking
            transactor.transact(
                threshold_staking_contract.setRoles,
                staking_provider,
                transactor.get_account().address,
                staking_provider,
                staking_provider,
            )

            transactor.transact(
                threshold_staking_contract.authorizationIncreased,
                staking_provider,
                0,
                min_stake_size,
            )

            # bonding
            transactor.transact(taco_application_contract.bondOperator, staking_provider, operator)

    return min_stake_size


def configure_amoy_root(transactor: Transactor, stake_size: int):
    """Configures MockTACoApplication on Amoy."""
    # Set up lynx stakes on Amoy
    poly_network = networks.polygon.amoy
    with poly_network.use_provider("infura"):
        deployments = contracts_from_registry(
            filepath=LYNX_REGISTRY_FILEPATH, chain_id=poly_network.chain_id
        )

        mock_taco_application_contract = deployments[project.MockPolygonChild.contract_type.name]

        for staking_provider, operator in LYNX_NODES.items():
            # staking
            transactor.transact(
                mock_taco_application_contract.updateAuthorization, staking_provider, stake_size
            )

            # bonding
            transactor.transact(
                mock_taco_application_contract.updateOperator, staking_provider, operator
            )


def main():
    check_plugins()
    transactor = Transactor()
    stake_size = configure_sepolia_root(transactor)
    configure_amoy_root(transactor, stake_size)
