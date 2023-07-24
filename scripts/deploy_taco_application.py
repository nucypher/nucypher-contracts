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
        _, _, t_staking, _, _, t_token = deploy_mocks(deployer)
    else:
        t_staking = deployments_config.get("t_staking")
        t_token = deployments_config.get("t_token")

    # TODO deploy proxy
    pre_app = project.TACoApplication.deploy(
        t_token,
        t_staking,
        deployments_config.get("pre_min_authorization"),
        deployments_config.get("pre_min_operator_seconds"),
        deployments_config.get("reward_duration"),
        deployments_config.get("deauthorization_duration"),
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return pre_app
