#!/usr/bin/python3
import filecmp
from pathlib import Path

from ape import accounts, networks, project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import ConflictResolution, merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "ci" / "child.yml"
UPGRADE_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "ci" / "upgrade-coordinator.yml"

UPGRADED_COORDINATOR_FILE_NAME = "ci-upgrade-coordinator.json"

ORIGINAL_DEPLOYMENT_ARTIFACT = ARTIFACTS_DIR / "ci.json"
UPGRADED_DEPLOYMENT_ARTIFACT = ARTIFACTS_DIR / UPGRADED_COORDINATOR_FILE_NAME
FINAL_DEPLOYMENT_ARTIFACT = ARTIFACTS_DIR / "ci-final.json"


def create_upgrade_coordinator_yaml(
    output_file: Path, taco_child_application_address: str, dkg_timeout: int
) -> None:
    """
    Creates a YAML file for the upgrade process.
    """
    yaml_text = f"""deployment:
  name: ci-upgrade-coordinator
  chain_id: 80002

artifacts:
  dir: ./deployment/artifacts/
  filename: {UPGRADED_COORDINATOR_FILE_NAME}

contracts:
  - Coordinator:
      constructor:
        _application: "{taco_child_application_address}"
        _dkgTimeout: {dkg_timeout}
    """
    with open(output_file, "w") as file:
        file.write(yaml_text)


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

    # dynamically create the YAML file for the upgrade of the Coordinator contract
    create_upgrade_coordinator_yaml(
        UPGRADE_PARAMS_FILEPATH,
        str(taco_child_application.address),
        coordinator.dkgTimeout(),
    )

    with networks.ethereum.local.use_provider("test"):
        test_account = accounts.test_accounts[0]
        upgrade_deployer = Deployer.from_yaml(
            filepath=UPGRADE_PARAMS_FILEPATH,
            verify=VERIFY,
            account=test_account,
            autosign=True,
        )

        upgraded_coordinator = upgrade_deployer.upgrade(project.Coordinator, coordinator.address)

    upgraded_deployments = [
        upgraded_coordinator,
    ]

    upgrade_deployer.finalize(deployments=upgraded_deployments)

    # merge registries
    merge_registries(
        registry_1_filepath=deployer.registry_filepath,
        registry_2_filepath=upgrade_deployer.registry_filepath,
        output_filepath=FINAL_DEPLOYMENT_ARTIFACT,
        force_conflict_resolution=ConflictResolution.USE_2,
    )

    # diff
    assert filecmp.cmp(ORIGINAL_DEPLOYMENT_ARTIFACT, FINAL_DEPLOYMENT_ARTIFACT, shallow=False)

    # remove created files
    deployer.registry_filepath.unlink()
    upgrade_deployer.registry_filepath.unlink()
    FINAL_DEPLOYMENT_ARTIFACT.unlink()
    UPGRADE_PARAMS_FILEPATH.unlink()
