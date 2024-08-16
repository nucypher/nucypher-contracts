#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR,
)
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "free-fee-model.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    free_fee_model = deployer.deploy(project.FreeFeeModel)

    deployments = [free_fee_model]

    deployer.finalize(deployments=deployments)
