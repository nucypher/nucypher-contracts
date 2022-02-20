#!/usr/bin/python3

import brownie
from brownie import SubscriptionManager, accounts, project, Contract, Wei
from brownie.project import compiler
from brownie.project.main import Project

from pathlib import Path

INITIAL_FEE_RATE = Wei("1 gwei")

def main(account_name : str = 'test'):
    deployer = accounts.load(account_name)

    # TODO: There has to be a better way to do this resolution. See #13
    current_project = project.get_loaded_projects().pop()
    brownie_packages = brownie._config._get_data_folder().joinpath('packages')
    oz_dependency_path = 'OpenZeppelin/openzeppelin-contracts@4.5.0/'
    oz = Project("OZ", brownie_packages.joinpath(oz_dependency_path))
    # FIXME: This is a workaround to save deployment data in the same project
    oz._build_path = current_project._build_path

    deployment_config = dict(gas_buffer=1.5,
                             required_confs=3,
                             publish_source=True)

    # ProxyAdmin
    proxy_admin = deployer.deploy(oz.ProxyAdmin, **deployment_config)

    # SubscriptionManager implementation
    subscription_manager_logic = deployer.deploy(SubscriptionManager,
                                                 **deployment_config)

    # TransparentUpgradeableProxy for SubscriptionManager (includes initialization)
    calldata = subscription_manager_logic.initialize.encode_input(INITIAL_FEE_RATE)
    constructor_args = (
        subscription_manager_logic.address,
        proxy_admin.address,
        calldata
    )
    transparent_proxy = deployer.deploy(oz.TransparentUpgradeableProxy,
                                        *constructor_args,
                                        **deployment_config)

    subscription_manager = Contract.from_abi("SubscriptionManager", transparent_proxy.address, subscription_manager_logic.abi, owner=None)
    return subscription_manager
