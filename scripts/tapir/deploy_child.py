#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
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

    January 8th, 2024
    ape run tapir deploy_child --network polygon:mumbai:infura
    ape-etherscan    0.6.10
    ape-infura       0.6.4
    ape-polygon      0.6.6
    ape-solidity     0.6.9
    eth-ape          0.6.19

    April 2nd, 2024
    ape run tapir deploy_child --network polygon:amoy:infura
    ape-etherscan    0.7.0
    ape-infura       0.7.2
    ape-polygon      0.7.2
    ape-solidity     0.7.1
    eth-ape          0.7.7
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    mock_polygon_child = deployer.deploy(project.MockPolygonChild)

    taco_child_application = deployer.deploy(project.TACoChildApplication)

    deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

    ritual_token = deployer.deploy(project.TapirRitualToken)
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
