#!/usr/bin/python3


from ape import networks, project
from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

TAPIR_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    check_plugins()
    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=TAPIR_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    initiator_role_hash = coordinator.INITIATOR_ROLE()
    transactor.transact(
        coordinator.grantRole,
        initiator_role_hash,
        transactor.get_account().address,  # <- new initiator
    )
