#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry, merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "upgrade-signing-coordinator.yml"
LYNX_REGISTRY = ARTIFACTS_DIR / "lynx.json"


def main():
    """This script upgrades SigningCoordinator on Lynx/Sepolia."""

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "lynx.json", chain_id=11155111)
    signing_coordinator = deployer.upgrade(
        project.SigningCoordinator, instances[project.SigningCoordinator.contract_type.name].address
    )

    deployments = [
        signing_coordinator,
    ]

    deployer.finalize(deployments=deployments)
    merge_registries(
        registry_1_filepath=LYNX_REGISTRY,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=LYNX_REGISTRY,
    )
