from ape import project
from ape.cli import get_user_selected_account
from deployment.constants import ARTIFACTS_DIR, LYNX_NODES
from deployment.registry import contracts_from_registry

ROOT_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"


def main():
    """
    Confirm lynx operator addresses on the Goerli side of the bridge

    ape run lynx confirm_operator_addresses --network ethereum:goerli:infura
    """

    deployer_account = get_user_selected_account()
    deployments = contracts_from_registry(filepath=ROOT_REGISTRY_FILEPATH)
    mock_polygon_root = deployments[project.MockPolygonRoot.contract_type.name]
    for _, operator in LYNX_NODES.items():
        mock_polygon_root.confirmOperatorAddress(operator, sender=deployer_account)
