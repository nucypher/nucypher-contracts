#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "upgrade-coordinator.yml"


def main():
    """
    This script upgrades Coordinator on Lynx/Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "lynx.json", chain_id=80002)

    coordinator = deployer.upgrade(
        project.Coordinator, instances[project.Coordinator.contract_type.name].address
    )

    deployments = [
        coordinator,
    ]

    deployer.finalize(deployments=deployments)
