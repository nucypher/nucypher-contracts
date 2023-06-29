#!/usr/bin/python3

import os

from ape import config, project, networks
from ape.cli import account_option, network_option, NetworkBoundCommand
from ape.utils import ZERO_ADDRESS

from ape_etherscan.utils import API_KEY_ENV_KEY_MAP

import click


@click.command(cls=NetworkBoundCommand)
@network_option()
@account_option()
@click.option('--currency', default=ZERO_ADDRESS)
@click.option('--rate', default=0)
@click.option('--verify/--no-verify', default=True)
def cli(network, account, currency, rate, verify):
    deployer = account #get_account(account_id)
    click.echo(f"Deployer: {deployer}")

    if rate and currency == ZERO_ADDRESS:
        raise ValueError("ERC20 contract address needed for currency")
    
    # Network
    ecosystem_name = networks.provider.network.ecosystem.name
    network_name = networks.provider.network.name
    provider_name = networks.provider.name
    click.echo(f"You are connected to network '{ecosystem_name}:{network_name}:{provider_name}'.")

    # TODO: Move this to a common deployment utilities module
    # Validate Etherscan verification parameters.
    # This import fails if called before the click network options are evaluated
    from scripts.utils import LOCAL_BLOCKCHAIN_ENVIRONMENTS
    is_public_deployment = network_name not in LOCAL_BLOCKCHAIN_ENVIRONMENTS
    if not is_public_deployment:
        verify = False
    elif verify:
        env_var_key = API_KEY_ENV_KEY_MAP.get(ecosystem_name)
        api_key = os.environ.get(env_var_key)
        if not api_key:
            raise ValueError(f"{env_var_key} is not set")

    # Use deployment information for currency, if possible
    try:
        deployments = config.deployments[ecosystem_name][network_name]
    except KeyError:
        pass  # TODO: Further validate currency address?
    else:
        try:
            currency = next(d for d in deployments if d["contract_type"] == currency)["address"]
        except StopIteration:
            pass
        
        try:
            stakes = next(d for d in deployments if d["contract_type"] == "StakeInfo")["address"]
        except StopIteration:
            raise ValueError("StakeInfo deployment needed")

    flat_rate_fee_model = project.FlatRateFeeModel.deploy(
        currency,
        rate,
        stakes,
        sender=deployer,
        publish=verify,
    )
    return flat_rate_fee_model