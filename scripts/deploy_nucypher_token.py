#!/usr/bin/python3
from ape import project
from scripts.utils import DEPLOYMENTS_CONFIG, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG
    nucypher_token_supply = deployments_config.get("nu_token_supply")

    nucypher_token = project.NuCypherToken.deploy(
        nucypher_token_supply,
        sender=deployer,
        publish_source=deployments_config.get("verify"),
    )
    return nucypher_token
