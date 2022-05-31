#!/usr/bin/python3
from brownie import SimplePREApplication, config
from scripts.utils import CURRENT_NETWORK, LOCAL_BLOCKCHAIN_ENVIRONMENTS, deploy_mocks, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]

    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        _, _, t_staking, _, _ = deploy_mocks(deployer)
    else:
        t_staking = network_config.get("t_staking")

    simple_pre = SimplePREApplication.deploy(
        t_staking,
        network_config.get("pre_min_authorization"),
        network_config.get("pre_min_operator_seconds"),
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return simple_pre
