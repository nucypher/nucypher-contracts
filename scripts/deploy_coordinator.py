#!/usr/bin/python3
from brownie import config, Coordinator

from scripts.utils import CURRENT_NETWORK, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]

    coordinator = Coordinator.deploy(
        network_config.get("ritual_timeout"),
        network_config.get("max_dkg_size"),
        network_config.get("pre_application"),
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return coordinator
