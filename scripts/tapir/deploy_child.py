#!/usr/bin/python3

from ape import project
from deployment.constants import CONSTRUCTOR_PARAMS_DIR, OZ_DEPENDENCY
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "child.yml"


def main():
    """
    This script deploys the Mock Tapir TACo Root Application,
    Proxied Tapir TACo Child Application, Tapir Ritual Token, and Tapir Coordinator.

    October 6th, 2023, Deployment:
    ape-run deploy_child --network polygon:mumbai:infura
    ape-etherscan             0.6.10
    ape-infura                0.6.4
    ape-polygon               0.6.6
    ape-solidity              0.6.9
    eth-ape                   0.6.20

    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin, deployer)

    taco_implementation = deployer.deploy(project.TapirTACoChildApplication)

    proxy = deployer.deploy(OZ_DEPENDENCY.TransparentUpgradeableProxy)
    taco_child_application = deployer.proxy(project.TACoChildApplication, proxy)

    deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

    ritual_token = deployer.deploy(project.TapirRitualToken)

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
