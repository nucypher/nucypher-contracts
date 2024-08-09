#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
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

    November 16, 2023, Update:
    ape-etherscan             0.6.10
    ape-infura                0.6.4
    ape-polygon               0.6.6
    ape-solidity              0.6.9
    eth-ape                   0.6.20

    March 28, 2024. Deployment on amoy (mumbai deprecated)
    ape-run deploy_child --network polygon:amoy:infura
    ape-etherscan             0.7.0
    ape-infura                0.7.2.dev2+g5215faf (customized local version for amoy support -
                                                   https://github.com/ApeWorX/ape-infura/pull/76)
    ape-polygon               0.7.2
    ape-solidity              0.7.1
    eth-ape                   0.7.7

    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    taco_child_application = deployer.deploy(project.TACoChildApplication)

    deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

    ritual_token = deployer.deploy(project.LynxRitualToken)

    coordinator = deployer.deploy(project.Coordinator)
    deployer.transact(taco_child_application.initialize, coordinator.address)

    global_allow_list = deployer.deploy(project.GlobalAllowList)

    deployments = [
        mock_polygon_child,
        taco_child_application,
        ritual_token,
        coordinator,
        global_allow_list,
    ]

    deployer.finalize(deployments=deployments)
