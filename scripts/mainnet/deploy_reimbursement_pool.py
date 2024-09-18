#!/usr/bin/python3

from ape import project, networks

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "reimbursement-pool.yml"
MAINNET_REGISTRY = ARTIFACTS_DIR / "mainnet.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    deployments = contracts_from_registry(
        filepath=MAINNET_REGISTRY, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]

    reimbursement_pool = deployer.deploy(project.ReimbursementPool)

    deployments = [reimbursement_pool]

    deployer.finalize(deployments=deployments)

    deployer.transact(reimbursement_pool.authorize, coordinator.address)
