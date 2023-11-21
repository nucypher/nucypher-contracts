#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = True
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "child.yml"


def main():

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    polygon_child = deployer.deploy(project.PolygonChild)

    taco_child_application = deployer.deploy(project.TACoChildApplication)

    deployer.transact(polygon_child.setChildApplication, taco_child_application.address)

    coordinator = deployer.deploy(project.Coordinator)

    deployer.transact(taco_child_application.initialize, coordinator.address)

    # Grant TREASURY_ROLE to Treasury Guild Multisig on Polygon (0xc3Bf49eBA094AF346830dF4dbB42a07dE378EeB6)
    TREASURY_ROLE = coordinator.TREASURY_ROLE()
    deployer.transact(
        coordinator.grantRole,
        TREASURY_ROLE,
        deployer.constants.TREASURY_GUILD_ON_POLYGON
    )

    # Grant INITIATOR_ROLE to Integrations Guild
    INITIATOR_ROLE = coordinator.INITIATOR_ROLE()
    deployer.transact(
        coordinator.grantRole,
        INITIATOR_ROLE,
        deployer.constants.INTEGRATIONS_GUILD_ON_POLYGON
    ) 
    # TODO: BetaProgramInitiator will be deployed separately, so council will grant the role later
    
    # Change Coordinator admin to Council on Polygon
    deployer.transact(
        coordinator.beginDefaultAdminTransfer,
        deployer.constants.THRESHOLD_COUNCIL_ON_POLYGON
    )
    # This requires the Council accepting the transfer by calling acceptDefaultAdminTransfer()

    global_allow_list = deployer.deploy(project.GlobalAllowList)

    deployments = [
        polygon_child,
        taco_child_application,
        coordinator,
        global_allow_list,
    ]

    deployer.finalize(deployments=deployments)
