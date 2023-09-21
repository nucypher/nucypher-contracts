#!/usr/bin/python3
from ape import project
from scripts.utils import get_account
from scripts.constants import DEPLOYMENTS_CONFIG


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG
    nucypher_token_supply = deployments_config.get("nu_token_supply")

    nucypher_token = project.NuCypherToken.deploy(
        nucypher_token_supply,
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return nucypher_token
