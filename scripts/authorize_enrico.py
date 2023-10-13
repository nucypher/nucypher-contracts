#!/usr/bin/python3
from pathlib import Path

import click
from ape import project
from ape.cli import NetworkBoundCommand, account_option, network_option
from eth_utils import to_checksum_address

from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins


@click.command(cls=NetworkBoundCommand)
@network_option(required=True)
@account_option()
@click.option(
    "--registry-filepath",
    "-r",
    help="Filepath to registry file",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
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
def cli(network, account, registry_filepath, ritual_id, enrico_address):
    check_plugins()
    print(f"network: {network}")
    transactor = Transactor(account=account)
    chain_id = project.chain_manager.chain_id
    deployments = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    global_allow_list = deployments[project.GlobalAllowList.contract_type.name]
    ritual_id = ritual_id or int(input("Enter ritual ID: "))
    addresses = [enrico_address or to_checksum_address(input("Enter address to authorize: "))]
    transactor.transact(global_allow_list.authorize, ritual_id, addresses)


if __name__ == "__main__":

    cli()
