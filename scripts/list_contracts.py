#!/usr/bin/python3


from itertools import groupby

import click
from ape.cli import ConnectedProviderCommand

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import read_registry
from deployment.utils import get_chain_name, registry_filepath_from_domain


def format_chain_name(chain_name):
    """
    Format the chain name to capitalize each word and join with slashes.
    """
    return "/".join(word.capitalize() for word in chain_name.split())


def get_registry_entries(selected_domain):
    """
    Parse the registry files for the given domain or all supported domains.
    """
    registry_entries = []

    for domain in SUPPORTED_TACO_DOMAINS:
        if selected_domain and selected_domain != domain:
            continue
        registry_filepath = registry_filepath_from_domain(domain=domain)
        entries = read_registry(filepath=registry_filepath)
        registry_entries.append((domain, entries))

    return registry_entries


def display_registry_entries(registry_entries):
    """
    Display registry entries grouped by chain ID.
    """
    for domain, entries in registry_entries:
        grouped_entries = groupby(entries, key=lambda entry: entry.chain_id)
        click.secho(f"\n{domain.capitalize()} Domain", fg="green")

        for chain_id, chain_entries in grouped_entries:
            chain_name = format_chain_name(get_chain_name(chain_id))
            click.secho(f"    {chain_name}", fg="yellow")

            for index, entry in enumerate(chain_entries, start=1):
                click.secho(f"        {index}. {entry.name} {entry.address}", fg="cyan")


@click.command(cls=ConnectedProviderCommand, name="list-contracts")
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
)
def cli(domain):
    registry_entries = get_registry_entries(domain)
    display_registry_entries(registry_entries)


if __name__ == "__main__":
    cli()
