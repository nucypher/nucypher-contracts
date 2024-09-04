#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"

def main():
    """
    Coordinator sets the ReimbursementPool

    ape run lynx coordinator_sets_reimbursement_pool --network polygon:amoy:infura
    """

    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=LYNX_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    reimbursement_pool = deployments[project.ReimbursementPool.contract_type.name]

    transactor.transact(coordinator.setReimbursementPool, reimbursement_pool.address)
