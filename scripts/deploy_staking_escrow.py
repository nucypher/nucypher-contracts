#!/usr/bin/python3
from brownie import StakingEscrow, config
from scripts.utils import CURRENT_NETWORK, LOCAL_BLOCKCHAIN_ENVIRONMENTS, get_account


def deploy_mocks():
    """This function should deploy nucypher_token and t_staking and return the
    corresponding contract addresses"""
    nucypher_token = None
    t_staking = None
    return nucypher_token, t_staking


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        nucypher_token, t_staking = deploy_mocks()
        work_lock = "0x0000000000000000000000000000000000000000"
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
