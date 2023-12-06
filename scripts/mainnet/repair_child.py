#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "repair-child.yml"


def main():
    """
    This script deploys latest TACoApplication and PolygonChild contracts on Polygon/Mainnet, setting
    the PolygonChild's child application to the new TACoApplication contract.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    polygon_child = deployer.deploy(project.PolygonChild)

    taco_child_application_implementation = deployer.deploy(project.TACoChildApplication)

    taco_child_application_proxy = '0xFa07aaB78062Fac4C36995bF28F6D677667973F5'
    deployer.transact(polygon_child.setChildApplication, taco_child_application_proxy)
    # PolygonChild must set the root tunnel on the repair root script after deployment and upgrade

    deployments = [
        polygon_child,
        taco_child_application_implementation,
    ]

    deployer.finalize(deployments=deployments)
