from pathlib import Path

import click
from ape import networks
from ape.cli import NetworkBoundCommand, network_option
from deployment.registry import contracts_from_registry
from deployment.utils import verify_contracts


@click.command(cls=NetworkBoundCommand)
@network_option(required=True)
@click.option(
    "--registry-filepath",
    "-r",
    help="Filepath to registry file",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    required=True,
)
def cli(network, registry_filepath):
    """Verify deployed contracts from a registry file."""
    contracts = contracts_from_registry(
        registry_filepath, chain_id=networks.active_provider.chain_id
    )
    verify_contracts(list(contracts.values()))
