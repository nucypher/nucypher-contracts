#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"

def main():
    """
    Coordinator approves the fee model for Free Fee Model

    ape run lynx coordinator_approve_free_fee_model --network polygon:amoy:infura
    """

    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=LYNX_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    free_fee_model = deployments[project.FreeFeeModel.contract_type.name]

    transactor.transact(coordinator.approveFeeModel, free_fee_model.address)
