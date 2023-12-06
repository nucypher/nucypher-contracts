#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import read_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "repair-root.yml"


def main():
    ethereum_network = networks.ethereum.mainnet
    polygon_network = networks.polygon.mainnet

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    with ethereum_network.use_provider("infura"):
        taco_application_implementation = deployer.deploy(project.TACoApplication)
        polygon_root = deployer.deploy(project.PolygonRoot)

        # Council multisig must call the next function
        # deployer.transact(taco_application.setChildApplication, polygon_root.address)


    with polygon_network.use_provider("infura"):
        polygon_child = project.PolygonChild.at('invalid')
        deployer.transact(polygon_child.setFxRootTunnel, polygon_root.address)


    deployments = [
        taco_application_implementation,
        polygon_root,
    ]

    deployer.finalize(deployments=deployments)

