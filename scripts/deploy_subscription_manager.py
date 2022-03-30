#!/usr/bin/python3

from pathlib import Path

import brownie
from brownie import SubscriptionManager, accounts, project, Contract, Wei
from brownie.project import compiler
from brownie.project.main import Project


INITIAL_FEE_RATE = Wei("1 gwei")


def main(account_name: str = "test"):
    deployer = accounts.load(account_name)
    oz = project.load("OpenZeppelin/openzeppelin-contracts@4.5.0/")

    proxy_admin = deployer.deploy(oz.ProxyAdmin)

    subscription_manager_logic = deployer.deploy(SubscriptionManager)
    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    transparent_proxy = oz.TransparentUpgradeableProxy.deploy(
        subscription_manager_logic.address, proxy_admin.address, calldata, {"from": deployer}
    )

    subscription_manager = Contract.from_abi(
        "SubscriptionManager", transparent_proxy.address, subscription_manager_logic.abi, owner=None
    )
    return subscription_manager
