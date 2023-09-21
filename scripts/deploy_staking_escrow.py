#!/usr/bin/python3
from ape import project
from scripts.utils import (
    deploy_mocks,
    get_account,
)
from scripts.constants import LOCAL_BLOCKCHAIN_ENVIRONMENTS, CURRENT_NETWORK, DEPLOYMENTS_CONFIG


def main(account_id=None):
    deployer = get_account(account_id)
    deployments_config = DEPLOYMENTS_CONFIG
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        nucypher_token, t_staking, _, work_lock, _, _ = deploy_mocks(deployer)
    else:
        nucypher_token = deployments_config.get("nu_token")
        t_staking = deployments_config.get("t_staking")
        work_lock = deployments_config.get("work_lock")

    staking_escrow = project.StakingEscrow.deploy(
        nucypher_token,
        work_lock,
        t_staking,
        sender=deployer,
        publish=deployments_config.get("verify"),
    )
    return staking_escrow
