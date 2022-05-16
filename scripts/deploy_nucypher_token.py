#!/usr/bin/python3
from brownie import NuCypherToken, config

from scripts.utils import CURRENT_NETWORK, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]
    nucypher_token_supply = network_config.get("nu_token_supply")

    nucypher_token = NuCypherToken.deploy(
        nucypher_token_supply,
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return nucypher_token
