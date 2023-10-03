#!/usr/bin/python3

from ape import project

from deployment.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
    CURRENT_NETWORK,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
    OZ_DEPENDENCY,
)
from deployment.params import Deployer
from deployment.registry import registry_from_ape_deployments
from deployment.utils import check_deployment_ready, verify_contracts

VERIFY = CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "child.yml"
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

    check_deployment_ready(registry_filepath=REGISTRY_FILEPATH)
    deployer = Deployer(params_path=CONSTRUCTOR_PARAMS_FILEPATH, publish=VERIFY)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin)

    taco_implementation = deployer.deploy(project.LynxTACoChildApplication)

    proxy = deployer.deploy(OZ_DEPENDENCY.TransparentUpgradeableProxy)
    taco_child_application = deployer.proxy(project.TACoChildApplication, proxy)

    deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

    ritual_token = deployer.deploy(project.LynxRitualToken)

    coordinator = deployer.deploy(project.Coordinator)

    deployer.transact(taco_child_application.initialize, coordinator.address)

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

    registry_from_ape_deployments(deployments=deployments, output_filepath=REGISTRY_FILEPATH)
    if VERIFY:
        verify_contracts(contracts=deployments)
