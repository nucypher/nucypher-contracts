#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "open_access_authorizer.yml"
LYNX = ARTIFACTS_DIR / "lynx.json"
TAPIR = ARTIFACTS_DIR / "tapir.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    open_access_authorizer = deployer.deploy(project.OpenAccessAuthorizer)
    deployments = [open_access_authorizer]
    deployer.finalize(deployments=deployments)

    for domain in (LYNX, TAPIR):
        merge_registries(
            registry_1_filepath=domain,
            registry_2_filepath=deployer.registry_filepath,
            output_filepath=domain,
        )
