#!/usr/bin/python3

from ape import project
from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "dashboard" / "root.yml"


def main():
    """
    This script deploys only the TACo Root Application for Dashboard development.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    taco_application = deployer.deploy(project.TACoApplication)

    mock_polygon_root = deployer.deploy(project.MockPolygonRoot)
    deployer.transact(taco_application.setChildApplication, mock_polygon_root.address)

    deployments = [
        taco_application,
        mock_polygon_root,
    ]

    deployer.finalize(deployments=deployments)
