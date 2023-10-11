#!/usr/bin/python3
from pathlib import Path

import click
from ape import networks, project
from ape.cli import NetworkBoundCommand, account_option, network_option
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
def cli(network, account, registry_filepath):
    check_plugins()
    transactor = Transactor(account)
    deployments = contracts_from_registry(
        filepath=registry_filepath, chain_id=networks.active_provider.chain_id
    )
    coordinator = deployments[project.Coordinator.contract_type.name]
    initiator_role_hash = coordinator.INITIATOR_ROLE()
    transactor.transact(
        coordinator.grantRole,
        initiator_role_hash,
        transactor.get_account().address,  # <- new initiator
    )
