#!/usr/bin/python3

from ape import project
from ape.cli import get_user_selected_account

from deployment.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
    CURRENT_NETWORK,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
    OZ_DEPENDENCY,
)
from deployment.registry import registry_from_ape_deployments
from deployment.utils import prepare_deployment, verify_contracts

VERIFY = CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "lynx-alpha-13-child-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"


def main():
    """
    This script deploys the Mock Lynx TACo Root Application,
    Proxied Lynx TACo Child Application, Lynx Ritual Token, and Lynx Coordinator.

    September 25, 2023, Deployment:
    ape-run deploy_lynx --network polygon:mumbai:infura
    ape-etherscan             0.6.10
    ape-infura                0.6.3
    ape-polygon               0.6.5
    ape-solidity              0.6.9
    eth-ape                   0.6.20
    """

    prepare_deployment(registry_filepath=REGISTRY_FILEPATH)
    deployer = Deployer(
        account=get_user_selected_account(),
        params_path=CONSTRUCTOR_PARAMS_FILEPATH,
        publish=VERIFY,
    )

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)
    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin)
    taco_implementation = deployer.deploy(project.LynxTACoChildApplication)
    proxy = deployer.deploy(OZ_DEPENDENCY.TransparentUpgradeableProxy)

    print("\nWrapping TACoChildApplication in proxy")
    taco_child_application = project.TACoChildApplication.at(proxy.address)

    print(f"\nSetting TACoChildApplication proxy ({taco_child_application.address})"
          f" as child application on MockPolygonChild ({mock_polygon_child.address})")
    mock_polygon_child.setChildApplication(
        taco_child_application.address,
        sender=deployer.get_account(),
    )

    ritual_token = deployer.deploy(project.LynxRitualToken)
    coordinator = deployer.deploy(project.Coordinator)

    print(f"\nInitializing TACoChildApplication proxy ({taco_child_application.address}) "
          f"with Coordinator ({coordinator.address})")
    taco_child_application.initialize(coordinator.address, sender=deployer.get_account())

    global_allow_list = deployer.deploy(project.GlobalAllowList)

    deployments = [
        mock_polygon_child,
        proxy_admin,
        taco_implementation,  # implementation (contract name is different than proxy contract)
        taco_child_application,  # proxy
        ritual_token,
        coordinator,
        global_allow_list,
    ]

    output_filepath = registry_from_ape_deployments(
        deployments=deployments, output_filepath=REGISTRY_FILEPATH
    )
    print(f"(i) Registry written to {output_filepath}!")

    if VERIFY:
        verify_contracts(contracts=deployments)
