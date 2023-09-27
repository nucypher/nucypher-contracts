from ape import networks, project
from deployment.constants import ARTIFACTS_DIR, LYNX_NODES
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

ROOT_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"
CHILD_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"


def configure_goerli_root(transactor: Transactor) -> int:
    """Configures ThresholdStaking and TACoApplication on Goerli."""
    deployments = contracts_from_registry(filepath=ROOT_REGISTRY_FILEPATH)

    # Set up lynx stakes on Goerli
    eth_network = networks.ethereum.goerli
    with eth_network.use_provider("infura"):
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


def configure_mumbai_root(transactor: Transactor, stake_size: int):
    """Configures MockTACoApplication on Mumbai."""
    deployments = contracts_from_registry(filepath=CHILD_REGISTRY_FILEPATH)

    # Set up lynx stakes on Mumbai
    poly_network = networks.polygon.mumbai
    with poly_network.use_provider("infura"):
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
    stake_size = configure_goerli_root(transactor)
    configure_mumbai_root(transactor, stake_size)
