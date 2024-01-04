#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "upgrades-root.yml"


def main():
    """
    This script upgrades TACoApplication in Lynx Sepolia.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    taco_app_proxy_address = "0x329bc9Df0e45f360583374726ccaFF003264a136"
    new_taco_app_implementation = deployer.upgrade(project.TACoApplication, taco_app_proxy_address)

    deployments = [
        new_taco_app_implementation,
    ]

    deployer.finalize(deployments=deployments)
