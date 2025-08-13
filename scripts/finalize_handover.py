#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress
from deployment.utils import check_plugins


@click.command(cls=ConnectedProviderCommand, name="finalize-handover")
@account_option()
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option("--ritual-id", "-r", help="Ritual ID to check", type=int, required=True)
@click.option(
    "--departing-provider",
    "-dp",
    help="The ethereum address of the departing staking provider.",
    required=True,
    type=ChecksumAddress(),
)
@click.option(
    "--auto",
    help="Automatically sign transactions.",
    is_flag=True,
)
def cli(
    domain,
    account,
    network,
    ritual_id,
    departing_provider,
    auto,
):
    """Finalize the handover."""

    # Setup
    check_plugins()
    click.echo(f"Connected to {network.name} network.")

    # Get the contracts from the registry
    coordinator_contract = registry.get_contract(domain=domain, contract_name="Coordinator")

    # Finalize the handover
    click.echo(
        f"Finalizing handover for ritual {ritual_id} and departing provider {departing_provider}..."
    )
    transactor = Transactor(account=account, autosign=auto)
    transactor.transact(
        coordinator_contract.finalizeHandover,
        ritual_id,
        departing_provider,
    )


if __name__ == "__main__":
    cli()
