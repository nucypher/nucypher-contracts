#!/usr/bin/python3
from pathlib import Path

import click
from ape import project
from ape.cli import (
    NetworkBoundCommand,
    account_option,
    network_option
)

from deployment.constants import LYNX_NODES
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
    "--duration",
    "-d",
    help="Duration of the ritual",
    type=int,
    default=86400,
    show_default=True,
)
def cli(registry_filepath, duration, network, account):
    check_plugins()
    print(f"Using network: {network}")
    print(f"Using account: {account}")
    transactor = Transactor(account=account)

    chain_id = project.chain_manager.chain_id
    deployments = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    coordinator = deployments[project.Coordinator.contract_type.name]

    global_allow_list = deployments[project.GlobalAllowList.contract_type.name]
    authority = transactor.get_account().address
    providers = list(sorted(LYNX_NODES.keys()))

    while True:
        transactor.transact(
            coordinator.initiateRitual,
            providers,
            authority,
            duration,
            global_allow_list.address
        )
        if not input("Another? [y/n] ").lower().startswith("y"):
            break


if __name__ == "__main__":
    cli()
