from pathlib import Path

import click
from ape import networks
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import get_contract_container, registry_filepath_from_domain, verify_contracts


@click.command(cls=ConnectedProviderCommand)
@network_option(required=True)
@click.option(
    "--contract-name",
    "-c",
    "contract_names",
    help="Contract to verify",
    type=click.STRING,
    required=True,
    multiple=True,
)
@click.option(
    "--domain",
    "-d",
    help="TACo domain; used for obtaining contract registry",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=False,
)
@click.option(
    "--registry-filepath",
    "-f",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    help="Registry filepath if the contract is not part of a common domain registry",
    required=False,
)
def cli(network, domain, contract_names, registry_filepath):
    """Verify a deployed contract."""
    if not (bool(registry_filepath) ^ bool(domain)):
        raise click.BadOptionUsage(
            option_name="--domain",
            message=(
                f"Provide either 'domain' or 'registry_filepath'; "
                f"got {domain}, {registry_filepath}"
            ),
        )

    registry_filepath = registry_filepath or registry_filepath_from_domain(domain=domain)
    chain_id = networks.active_provider.chain_id
    contracts = contracts_from_registry(registry_filepath, chain_id=chain_id)

    contract_instances = []
    for contract_name in contract_names:
        try:
            contract_instance = contracts[contract_name]
        except KeyError:
            raise ValueError(
                f"Contract '{contract_name}' not found in registry, '{registry_filepath}', "
                f"for chain {chain_id}"
            )

        # check whether contract is a proxy
        proxy_info = networks.provider.network.ecosystem.get_proxy_info(contract_instance.address)
        if proxy_info:
            # we have an instance of a proxy contract, but need the underlying implementation
            print(
                f"Proxy contract detected; verifying implementation contract at {proxy_info.target}"
            )
            contract_container = get_contract_container(contract_instance.contract_type.name)
            contract_instance = contract_container.at(proxy_info.target)

        contract_instances.append(contract_instance)

    verify_contracts(contract_instances)


if __name__ == "__main__":
    cli()
