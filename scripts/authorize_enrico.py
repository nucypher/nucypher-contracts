#!/usr/bin/python3

import click
from ape import project
from ape.cli import ConnectedProviderCommand, account_option, network_option
from eth_utils import to_checksum_address

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins, registry_filepath_from_domain


@click.command(cls=ConnectedProviderCommand)
@network_option(required=True)
@account_option()
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option(
    "--ritual-id",
    "-i",
    help="Ritual ID",
    type=int,
    required=False,
)
@click.option(
    "--enrico-address",
    "-e",
    help="Enrico address",
    type=str,
    required=False,
)
def cli(network, account, domain, ritual_id, enrico_address):
    check_plugins()
    transactor = Transactor(account=account)
    registry_filepath = registry_filepath_from_domain(domain=domain)
    chain_id = project.chain_manager.chain_id
    deployments = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    global_allow_list = deployments[project.GlobalAllowList.contract_type.name]
    ritual_id = ritual_id or int(input("Enter ritual ID: "))
    addresses = [enrico_address or to_checksum_address(input("Enter address to authorize: "))]
    transactor.transact(global_allow_list.authorize, ritual_id, addresses)


if __name__ == "__main__":
    cli()
