#!/usr/bin/python3

from ape import project, networks

from deployment.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
)
from deployment.params import Deployer, Transactor
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "tapir-free-fee-model.yml"
TAPIR_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    deployments = contracts_from_registry(
        filepath=TAPIR_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    transactor = Transactor()

    free_fee_model = deployer.deploy(project.FreeFeeModel)
    coordinator = deployments[project.Coordinator.contract_type.name]
    transactor.transact(coordinator.approveFeeModel, free_fee_model.address)
    deployments = [free_fee_model]

    deployer.finalize(deployments=deployments)
