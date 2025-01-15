#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"

def main():
    """
    Coordinator approves the fee model for StandardSubscription

    ape run lynx coordinator_approve_fee_model --network polygon:amoy:infura
    """

    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=LYNX_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    std_subscription = deployments[project.StandardSubscription.contract_type.name]

    # Grant TREASURY_ROLE
    TREASURY_ROLE = coordinator.TREASURY_ROLE()
    transactor.transact(
        coordinator.grantRole,
        TREASURY_ROLE,
        transactor.get_account().address
    )
    transactor.transact(coordinator.approveFeeModel, std_subscription.address)
