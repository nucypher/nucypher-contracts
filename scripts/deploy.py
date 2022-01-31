#!/usr/bin/python3

import brownie
from brownie import SubscriptionManager, accounts, Contract, Wei
from brownie.project.main import Project

INITIAL_FEE_RATE = Wei("1 gwei")

def main():
    deployer = accounts.load('test')

    brownie_packages = brownie._config._get_data_folder().joinpath('packages')
    oz_dependency_path = 'OpenZeppelin/openzeppelin-contracts@4.4.2/'
    oz = Project("OZ", brownie_packages.joinpath(oz_dependency_path))
    
    proxy_admin = deployer.deploy(oz.ProxyAdmin)

    subscription_manager_logic = deployer.deploy(SubscriptionManager)
    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    transparent_proxy = oz.TransparentUpgradeableProxy.deploy(
        subscription_manager_logic.address,
        proxy_admin.address,
        calldata,
        {'from': deployer})

    subscription_manager = Contract.from_abi("SubscriptionManager", transparent_proxy.address, subscription_manager_logic.abi, owner=None)
    return subscription_manager
