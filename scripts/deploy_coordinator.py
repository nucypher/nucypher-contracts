#!/usr/bin/python3
from ape import project
from ape.cli import get_user_selected_account
from scripts.constants import DEPLOYMENTS_CONFIG


def main(account_id=None):
    deployer = get_user_selected_account()
    deployments_config = DEPLOYMENTS_CONFIG

    coordinator = project.Coordinator.deploy(
        deployments_config.get("taco_child_contract"),
        deployments_config.get("ritual_timeout"),
        deployments_config.get("max_dkg_size"),
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return coordinator
