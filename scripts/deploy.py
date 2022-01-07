#!/usr/bin/python3

from brownie import SubscriptionManager, accounts

def main():
    deployer = accounts.load('test')
    return SubscriptionManager.deploy({'from':deployer})
