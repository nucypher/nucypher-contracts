#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "upgrade-taco-child-app.yml"


def main():
    """
    This script upgrades TACoChildApplication contract for Tapir on Polygon Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "tapir.json", chain_id=80002)

    taco_child_application = deployer.upgrade(
        project.TACoChildApplication,
        instances[project.TACoChildApplication.contract_type.name].address,
    )

    deployments = [
        taco_child_application,
    ]

    deployer.finalize(deployments=deployments)
