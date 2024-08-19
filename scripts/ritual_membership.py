import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain


@click.command(cls=ConnectedProviderCommand)
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option(
    "--staking-provider-address",
    "-p",
    help="Staking provider address to check",
    type=ChecksumAddress,
    required=True,
)
def cli(network, domain, staking_provider_address):
    """Lists all the active rituals that a staking provider is participating in."""
    registry_filepath = registry_filepath_from_domain(domain=domain)
    contracts = contracts_from_registry(
        registry_filepath, chain_id=networks.active_provider.chain_id
    )

    provider_checksum_address = to_checksum_address(staking_provider_address)
    # lower used for comparing against sorted list
    provider_checksum_address_lower = provider_checksum_address.lower()

    coordinator = project.Coordinator.at(contracts["Coordinator"].address)
    num_rituals = coordinator.numberOfRituals()

    ritual_memberships = []
    for ritual_id in range(0, num_rituals):
        if not coordinator.isRitualActive(ritual_id):
            continue

        participants = coordinator.getParticipants(ritual_id)
        for participant in participants:
            provider = participant.provider
            if provider == provider_checksum_address:
                ritual_memberships.append(ritual_id)
                break
            if provider_checksum_address_lower < provider:
                # list of participants is sorted so stop early if already passed
                break

    if not ritual_memberships:
        print(f"\nStaking provider {provider_checksum_address} is not part of any rituals")
        return

    print("\nActive Ritual Memberships:")
    for ritual_id in ritual_memberships:
        print(f"\t- ID: #{ritual_id}")
