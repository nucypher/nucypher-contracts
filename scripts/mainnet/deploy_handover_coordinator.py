#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "child.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # NuCo Multisig owns contract so it must do the proxy upgrade
    coordinator_implementation = deployer.deploy(project.HandoverCoordinator)

    deployments = [
        coordinator_implementation,
    ]

    deployer.finalize(deployments=deployments)
