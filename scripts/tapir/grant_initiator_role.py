#!/usr/bin/python3


from ape import project

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

ROOT_REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    check_plugins()
    transactor = Transactor()
    deployments = contracts_from_registry(filepath=ROOT_REGISTRY_FILEPATH)
    coordinator = deployments[project.Coordinator.contract_type.name]
    initiator_role_hash = coordinator.INITIATOR_ROLE()
    transactor.transact(
        coordinator.grantRole,
        initiator_role_hash,
        transactor.get_account().address,  # <- new initiator
    )
