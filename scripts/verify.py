import click
from ape import networks
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain, verify_contracts


@click.command(cls=ConnectedProviderCommand)
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
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
