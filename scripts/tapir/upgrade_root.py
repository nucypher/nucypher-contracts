#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "upgrade-root.yml"


def main():
    """
    This script upgrades root contracts for Tapir on Eth Sepolia.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "tapir.json", chain_id=11155111)

    mock_threshold_staking = deployer.deploy(project.TestnetThresholdStaking)

    taco_application = deployer.upgrade(
        project.TACoApplication,
        instances[project.TACoApplication.contract_type.name].address,
    )

    deployer.transact(mock_threshold_staking.setApplication, taco_application.address)

    mock_polygon_root = deployer.deploy(project.MockPolygonRoot)
    deployer.transact(taco_application.setChildApplication, mock_polygon_root.address)

    deployments = [
        mock_threshold_staking,
        taco_application,
        mock_polygon_root,
    ]

    deployer.finalize(deployments=deployments)
