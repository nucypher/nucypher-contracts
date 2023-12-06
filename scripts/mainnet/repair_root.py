#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import read_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "repair-root.yml"


def main():

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    taco_application_implementation = deployer.deploy(project.TACoApplication)
    polygon_root = deployer.deploy(project.PolygonRoot)

    # Council multisig upgrades TACoApplication with new implementation.
    # Also, council must set the child application with new PolygonRoot
    # deployer.transact(taco_application.setChildApplication, polygon_root.address)

    # Pending steps to be performed in Polygon
    #     polygon_child = project.PolygonChild.at('invalid')
    #     deployer.transact(polygon_child.setFxRootTunnel, polygon_root.address)

    deployments = [
        taco_application_implementation,
        polygon_root,
    ]

    deployer.finalize(deployments=deployments)

