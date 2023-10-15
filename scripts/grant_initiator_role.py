#!/usr/bin/python3

import click
from ape import networks, project
from ape.cli import NetworkBoundCommand, account_option, network_option
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins, registry_filepath_from_domain


@click.command(cls=NetworkBoundCommand)
@network_option(required=True)
@account_option()
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.STRING,
    required=True,
)
def cli(network, account, domain):
    check_plugins()
    transactor = Transactor(account)
    registry_filepath = registry_filepath_from_domain(domain=domain)
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


if __name__ == "__main__":
    cli()
