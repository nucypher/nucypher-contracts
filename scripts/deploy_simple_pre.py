#!/usr/bin/python3
from ape import project
from scripts.utils import (
    CURRENT_NETWORK,
    DEPLOYMENTS_CONFIG,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
    deploy_mocks,
    get_account,
)


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG

    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        _, _, t_staking, _, _ = deploy_mocks(deployer)
    else:
        t_staking = deployments_config.get("t_staking")

    simple_pre = project.SimplePREApplication.deploy(
        t_staking,
        deployments_config.get("pre_min_authorization"),
        deployments_config.get("pre_min_operator_seconds"),
        sender=deployer,
        publish_source=deployments_config.get("verify"),
    )
    return simple_pre
