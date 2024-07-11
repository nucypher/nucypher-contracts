#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "free-fee-model.yml"
LYNX_REGISTRY = ARTIFACTS_DIR / "lynx.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    free_fee_model = deployer.deploy(project.FreeFeeModel)

    deployments = [free_fee_model]

    deployer.finalize(deployments=deployments)
