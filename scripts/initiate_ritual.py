#!/usr/bin/python3

import click
from ape import project
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment.constants import LYNX, LYNX_NODES, SUPPORTED_TACO_DOMAINS, TAPIR, TAPIR_NODES
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
    "--duration",
    "-t",
    help="Duration of the ritual",
    type=int,
    default=86400,
    show_default=True,
)
@click.option(
    "--access-controller",
    "-a",
    help="global allow list or open access authorizer.",
    type=click.Choice(["GlobalAllowList", "OpenAccessAuthorizer"]),
    required=True,
)
def cli(domain, duration, network, account, access_controller):
    check_plugins()
    print(f"Using network: {network}")
    print(f"Using domain: {domain}")
    print(f"Using account: {account}")
    transactor = Transactor(account=account)

    if domain == LYNX:
        providers = list(sorted(LYNX_NODES.keys()))
    elif domain == TAPIR:
        providers = list(sorted(TAPIR_NODES.keys()))
    else:
        # mainnet sampling not currently supported
        raise ValueError(f"Sampling of providers not supported for domain '{domain}'")

    registry_filepath = registry_filepath_from_domain(domain=domain)

    chain_id = project.chain_manager.chain_id
    deployments = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    coordinator = deployments[project.Coordinator.contract_type.name]

    access_controller = deployments[getattr(project, access_controller).contract_type.name]
    authority = transactor.get_account().address

    while True:
        transactor.transact(
            coordinator.initiateRitual, providers, authority, duration, access_controller.address
        )
        if not input("Another? [y/n] ").lower().startswith("y"):
            break


if __name__ == "__main__":
    cli()
