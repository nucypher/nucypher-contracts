#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry, merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "upgrade-coordinator.yml"
TAPIR_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    """
    This script upgrades Coordinator on Tapir/Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "tapir.json", chain_id=80002)

    implementation = deployer.deploy(project.Coordinator)
    # latest reinitializer function used for most recent upgrade - reinitializer(2)
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
        registry_1_filepath=TAPIR_REGISTRY_FILEPATH,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=TAPIR_REGISTRY_FILEPATH,
    )
