#!/usr/bin/python3
from ape import accounts, networks, project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "ci" / "child.yml"


def main():
    with networks.ethereum.local.use_provider("test"):
        test_account = accounts.test_accounts[0]

        deployer = Deployer.from_yaml(
            filepath=CONSTRUCTOR_PARAMS_FILEPATH,
            verify=VERIFY,
            account=test_account,
            autosign=True,
        )

        mock_polygon_child = deployer.deploy(project.MockPolygonChild)

        taco_child_application = deployer.deploy(project.TACoChildApplication)

        deployer.transact(mock_polygon_child.setChildApplication, taco_child_application.address)

        ritual_token = deployer.deploy(project.LynxRitualToken)

        coordinator = deployer.deploy(project.Coordinator)

        global_allow_list = deployer.deploy(project.GlobalAllowList)

    deployments = [
        mock_polygon_child,
        taco_child_application,
        ritual_token,
        coordinator,
        global_allow_list,
    ]

    deployer.finalize(deployments=deployments)

    # remove registry file now that task is complete
    deployer.registry_filepath.unlink()
