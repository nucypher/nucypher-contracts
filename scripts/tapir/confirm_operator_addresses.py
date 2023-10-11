#!/usr/bin/python3

from ape import networks, project
from deployment.constants import ARTIFACTS_DIR, TAPIR_NODES
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

REGISTRY_FILEPATH = ARTIFACTS_DIR / "tapir.json"


def main():
    """
    Confirm tapir operator addresses on the Sepolia side of the bridge

    ape run tapir confirm_operator_addresses --network ethereum:sepolia:infura
    """
    check_plugins()
    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    mock_polygon_root = deployments[project.MockPolygonRoot.contract_type.name]
    for _, operator in TAPIR_NODES.items():
        transactor.transact(mock_polygon_root.confirmOperatorAddress, operator)
