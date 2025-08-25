#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "redeploy-bqeth.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # NuCo Multisig owns contract so it must do the proxy upgrade
    new_implementation = deployer.deploy(project.StandardSubscription)

    # TODO Careful with contract registry since address should be the proxy address,
    #  not the implementation address - basically only update abi in contract registry
    deployments = [
        new_implementation,
    ]

    deployer.finalize(deployments=deployments)
