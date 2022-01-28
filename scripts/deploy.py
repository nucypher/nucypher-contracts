#!/usr/bin/python3

from brownie import SubscriptionManager, accounts, Wei

def main():
    deployer = accounts.load('test')
    subscription_manager = SubscriptionManager.deploy({'from':deployer})
    subscription_manager.initialize(Wei("1 gwei"))
    return subscription_manager
