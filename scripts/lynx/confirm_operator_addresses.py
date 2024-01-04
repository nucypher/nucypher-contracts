#!/usr/bin/python3


from ape import networks, project

from deployment.constants import ARTIFACTS_DIR, LYNX_NODES
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"


def main():
    """
    Confirm lynx operator addresses on the Sepolia side of the bridge

    ape run lynx confirm_operator_addresses --network ethereum:sepolia:infura
    """
    check_plugins()
    transactor = Transactor()
    deployments = contracts_from_registry(
        filepath=LYNX_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    mock_polygon_root = deployments[project.MockPolygonRoot.contract_type.name]
    for _, operator in LYNX_NODES.items():
        transactor.transact(mock_polygon_root.confirmOperatorAddress, operator)
