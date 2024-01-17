#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "beta_program_initiator.yml"
MAINNET_REGISTRY = ARTIFACTS_DIR / "mainnet.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    beta_program_initiator = deployer.deploy(project.BetaProgramInitiator)
    deployments = [beta_program_initiator]
    deployer.finalize(deployments=deployments)
    merge_registries(
        registry_1_filepath=MAINNET_REGISTRY,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=MAINNET_REGISTRY,
    )
