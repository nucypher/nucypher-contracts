#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "upgrade-root.yml"


def main():
    """
    This script upgrades TACoApplication in Tapir Sepolia.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    taco_app_proxy_address = "0xCcFf527698E78a536d80695D9Af4F4f3265ADA05"
    new_taco_app_implementation = deployer.upgrade(project.TACoApplication, taco_app_proxy_address)

    deployments = [
        new_taco_app_implementation,
    ]

    deployer.finalize(deployments=deployments)
