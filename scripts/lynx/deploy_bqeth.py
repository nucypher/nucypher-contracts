#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer
from deployment.registry import merge_registries

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "bqeth.yml"
LYNX_REGISTRY = ARTIFACTS_DIR / "lynx.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    global_allow_list = deployer.deploy(project.GlobalAllowList)

    bqeth_subscription = deployer.deploy(project.BqETHSubscription)

    deployments = [global_allow_list, bqeth_subscription]

    deployer.finalize(deployments=deployments)

    deployer.transact(bqeth_subscription.setAdopter, deployer.get_account().address)

    merge_registries(
        registry_1_filepath=LYNX_REGISTRY,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=LYNX_REGISTRY,
    )
