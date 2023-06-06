#!/usr/bin/python3
from ape import project
from ape.cli import get_user_selected_account

from scripts.utils import DEPLOYMENTS_CONFIG, get_account


def main(account_id=None):
    deployer = get_user_selected_account()
    deployments_config = DEPLOYMENTS_CONFIG

    coordinator = project.Coordinator.deploy(
        deployments_config.get("stake_info_contract"),
        deployments_config.get("ritual_timeout"),
        deployments_config.get("max_dkg_size"),
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return coordinator
