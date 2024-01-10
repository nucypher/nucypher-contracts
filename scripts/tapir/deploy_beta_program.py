#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "beta_program_initiator.yml"
TAPIR_REGISTRY = ARTIFACTS_DIR / "tapir.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    beta_program_initiator = deployer.deploy(project.BetaProgramInitiator)
    deployments = [beta_program_initiator]
    deployer.finalize(deployments=deployments)
    merge_registries(
        registry_1_filepath=TAPIR_REGISTRY,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=TAPIR_REGISTRY,
    )
