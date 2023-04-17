#!/usr/bin/python3
from ape import project
from scripts.utils import DEPLOYMENTS_CONFIG, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG
    testnet_staking = project.TestnetThresholdStaking.deploy(
        sender=deployer,
        publish_source=deployments_config.get("verify"),
    )
    return testnet_staking
