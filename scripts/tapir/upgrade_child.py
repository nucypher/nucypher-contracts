#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "upgrade-child.yml"


def main():
    """
    This script upgrades child contracts for Tapir on Polygon Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "tapir.json", chain_id=80002)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    taco_child_application = deployer.upgrade(
        project.TACoChildApplication,
        instances[project.TACoChildApplication.contract_type.name].address,
    )

    deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

    coordinator = deployer.upgrade(
        project.Coordinator, instances[project.Coordinator.contract_type.name].address
    )

    deployments = [
        mock_polygon_child,
        taco_child_application,
        coordinator,
    ]

    deployer.finalize(deployments=deployments)
