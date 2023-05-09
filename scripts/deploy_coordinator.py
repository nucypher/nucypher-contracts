#!/usr/bin/python3
from ape import project
from scripts.utils import DEPLOYMENTS_CONFIG, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG

    coordinator = project.Coordinator.deploy(
        deployments_config.get("pre_application"),
        deployments_config.get("ritual_timeout"),
        deployments_config.get("max_dkg_size"),
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return coordinator
