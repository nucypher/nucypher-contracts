#!/usr/bin/python3

from ape import project
from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "upgrade-root.yml"


def main():
    """
    This script deploys latest TACoApplication contract on Mainnet.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # we can only deploy this new implementation; only the Council can upgrade the
    # proxy contract to point to this implementation
    new_taco_app_implementation = deployer.deploy(
        project.TACoApplication,
    )

    deployments = [
        new_taco_app_implementation,
    ]

    deployer.finalize(deployments=deployments)
