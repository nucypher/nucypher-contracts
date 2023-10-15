import click
from ape import networks
from ape.cli import NetworkBoundCommand, network_option
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain, verify_contracts


@click.command(cls=NetworkBoundCommand)
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.STRING,
    required=True,
)
def cli(network, domain):
    """Verify deployed contracts from a registry file."""
    registry_filepath = registry_filepath_from_domain(domain=domain)
    contracts = contracts_from_registry(
        registry_filepath, chain_id=networks.active_provider.chain_id
    )
    verify_contracts(list(contracts.values()))


if __name__ == "__main__":
    cli()
