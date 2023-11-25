#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "legacy.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    staking_escrow = deployer.deploy(project.StakingEscrow)

    deployments = [
        staking_escrow,
    ]

    deployer.finalize(deployments=deployments)
