#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "subscription_manager.yml"
LYNX = ARTIFACTS_DIR / "lynx.json"
TAPIR = ARTIFACTS_DIR / "tapir.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    subscription_manager = deployer.deploy(project.SubscriptionManager)
    deployments = [subscription_manager]
    deployer.finalize(deployments=deployments)

    for domain in (LYNX, TAPIR):
        merge_registries(
            registry_1_filepath=domain,
            registry_2_filepath=deployer.registry_filepath,
            output_filepath=domain,
        )
