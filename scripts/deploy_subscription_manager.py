#!/usr/bin/python3
from brownie import Contract, SubscriptionManager, Wei, accounts, network, project

INITIAL_FEE_RATE = Wei("1 gwei")
# Can add local forks of networks here
LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["development"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]


def get_account(id):
    if network.show_active() in PRODUCTION_ENVIRONMENTS:
        if id is None:
            raise ValueError("Must specify account id when deploying to production networks")
        else:
            return accounts.load(id)

    if network.show_active() in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        return accounts[0]


def main(id=None):
    deployer = get_account(id)
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
