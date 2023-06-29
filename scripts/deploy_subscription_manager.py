#!/usr/bin/python3
from ape import project
from scripts.utils import get_account
from web3 import Web3

INITIAL_FEE_RATE = Web3.to_wei(1, "gwei")


def main(id=None):
    deployer = get_account(id)
    dependency = project.dependencies["openzeppelin"]["4.9.1"]

    proxy_admin = deployer.deploy(dependency.ProxyAdmin)

    subscription_manager_logic = deployer.deploy(project.SubscriptionManager)
    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    transparent_proxy = dependency.TransparentUpgradeableProxy.deploy(
        subscription_manager_logic.address, proxy_admin.address, calldata, sender=deployer
    )

    subscription_manager = project.SubscriptionManager.at(transparent_proxy.address)
    return subscription_manager
