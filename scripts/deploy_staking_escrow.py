#!/usr/bin/python3
from brownie import StakingEscrow, config
from scripts.utils import CURRENT_NETWORK, LOCAL_BLOCKCHAIN_ENVIRONMENTS, deploy_mocks, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        nucypher_token, t_staking, work_lock, _ = deploy_mocks(deployer)
    else:
        nucypher_token = network_config.get("nu_token")
        t_staking = network_config.get("t_staking")
        work_lock = network_config.get("work_lock")

    staking_escrow = StakingEscrow.deploy(
        nucypher_token,
        work_lock,
        t_staking,
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return staking_escrow
