#!/usr/bin/python3

from ape import project
from deployment.constants import CONSTRUCTOR_PARAMS_DIR, OZ_DEPENDENCY
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "child.yml"


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

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin, deployer)

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

    deployer.finalize(deployments=deployments)
