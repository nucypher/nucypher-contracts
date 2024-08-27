#!/usr/bin/python3

from ape import project, networks

from deployment.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
)
from deployment.params import Deployer
from deployment.registry import contracts_from_registry, merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "free-fee-model.yml"
TAPIR_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    deployments = contracts_from_registry(
        filepath=TAPIR_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    free_fee_model = deployer.deploy(project.FreeFeeModel)
    deployments = [free_fee_model]

    deployer.finalize(deployments=deployments)
    merge_registries(
        registry_1_filepath=TAPIR_REGISTRY_FILEPATH,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=TAPIR_REGISTRY_FILEPATH,
    )
