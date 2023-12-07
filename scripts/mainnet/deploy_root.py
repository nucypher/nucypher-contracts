#!/usr/bin/python3

from ape import project, networks

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import read_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "root.yml"


def main():
    current_mainnet_registry = read_registry(ARTIFACTS_DIR / "mainnet-child.json")
    polygon_chain_id = 137
    polygon_child_name = "PolygonChild"
    polygon_childs = [
        entry
        for entry in current_mainnet_registry
        if entry.chain_id == polygon_chain_id and entry.name == polygon_child_name
    ]
    if len(polygon_childs) != 1:
        raise ValueError("Mainnet root deployment requires valid child deployment first")

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # TODO: Workaround to provide PolygonChild address from existing registry
    polygon_child = polygon_childs.pop()
    deployer.constructor_parameters.parameters["PolygonRoot"][
        "_fxChildTunnel"
    ] = polygon_child.address

    taco_application = deployer.deploy(project.TACoApplication)

    polygon_root = deployer.deploy(project.PolygonRoot)

    # This line was missing from the original script
    # with networks.polygon.mainnet.use_provider("infura"):
    #     polygon_child = project.PolygonChild.at('invalid')
    #     deployer.transact(polygon_child.setFxRootTunnel, polygon_root.address)

    # Need to set child application before transferring ownership
    deployer.transact(taco_application.setChildApplication, polygon_root.address)
    deployer.transact(
        taco_application.transferOwnership, deployer.constants.THRESHOLD_COUNCIL_ETH_MAINNET
    )

    deployments = [
        taco_application,
        polygon_root,
    ]

    deployer.finalize(deployments=deployments)
