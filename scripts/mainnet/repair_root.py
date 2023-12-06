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

    # The following steps we performed manually on Polygon
    # In [1]: polygon_child_address = "0x1f5C5fd6A66723fA22a778CC53263dd3FA6851E5"
    # In [2]: polygon_child = project.PolygonChild.at(polygon_child_address)
    # In [3]: polygon_root_address = "0x51825d6e893c51836dC9C0EdF3867c57CD0cACB3"
    # In [4]: polygon_child.setFxRootTunnel(polygon_root_address, sender=...)

    deployments = [
        taco_application_implementation,
        polygon_root,
    ]

    deployer.finalize(deployments=deployments)

