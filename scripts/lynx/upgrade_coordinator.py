#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry, merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "upgrade-coordinator.yml"
LYNX_REGISTRY = ARTIFACTS_DIR / "lynx.json"


def main():
    """
    This script upgrades Coordinator on Lynx/Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "lynx.json", chain_id=80002)

    implementation = deployer.deploy(project.Coordinator)
    # encoded_initializer_function = implementation.initializeNumberOfRituals.encode_input()
    encoded_initializer_function = b""
    coordinator = deployer.upgradeTo(
        implementation,
        instances[project.Coordinator.contract_type.name].address,
        encoded_initializer_function,
    )

    deployments = [
        coordinator,
    ]

    deployer.finalize(deployments=deployments)
    merge_registries(
        registry_1_filepath=LYNX_REGISTRY,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=LYNX_REGISTRY,
    )
