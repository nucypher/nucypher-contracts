#!/usr/bin/python3
from ape import project
from scripts.utils import get_account
from scripts.constants import DEPLOYMENTS_CONFIG


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG
    testnet_staking = project.TestnetThresholdStaking.deploy(
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return testnet_staking
