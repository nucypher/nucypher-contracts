#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry

TAPIR_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"

def main():
    """
    Coordinator approves the fee model for BqETHSubscription

    ape run tapir coordinator_approve_fee_model --network polygon:amoy:infura
    """

    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=TAPIR_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    bqeth_subscription = deployments[project.BqETHSubscription.contract_type.name]

    # Grant TREASURY_ROLE
    TREASURY_ROLE = coordinator.TREASURY_ROLE()
    transactor.transact(
        coordinator.grantRole,
        TREASURY_ROLE,
        transactor.get_account().address
    )
    transactor.transact(coordinator.approveFeeModel, bqeth_subscription.address)
