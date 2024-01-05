#!/usr/bin/python3

from ape import project, networks

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "redeploy-taco-app.yml"


def main():

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    taco_application_implementation = deployer.deploy(project.TACoApplication)

    deployments = [
        taco_application_implementation,
    ]

    deployer.finalize(deployments=deployments)

