#!/usr/bin/python3

from brownie import TestnetThresholdStaking, config

from scripts.utils import CURRENT_NETWORK, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]
    testnet_staking = TestnetThresholdStaking.deploy(
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return testnet_staking
