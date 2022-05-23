#!/usr/bin/python3
from brownie import Adjudicator, config
from scripts.utils import CURRENT_NETWORK, LOCAL_BLOCKCHAIN_ENVIRONMENTS, deploy_mocks, get_account


def main(account_id=None):
    deployer = get_account(account_id)
    network_config = config["networks"][CURRENT_NETWORK]

    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        _, _, _, staking_escrow = deploy_mocks(deployer)
    else:
        staking_escrow = network_config.get("staking_escrow")

    adjudicator = Adjudicator.deploy(
        staking_escrow,
        network_config.get("adjudicator_hash_algorithm"),
        network_config.get("adjudicator_base_penalty"),
        network_config.get("adjudicator_penalty_history_coefficient"),
        network_config.get("adjudicator_percentage_penalty_coefficient"),
        network_config.get("adjudicator_reward_coefficient"),
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )
    return adjudicator
