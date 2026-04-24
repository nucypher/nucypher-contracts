#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress
from deployment.utils import check_plugins

STATUS_ENDPOINT = "https://mainnet.nucypher.network:9151/status/?json=true"

def check_incoming_provider(incoming_provider: str) -> bool:
    """Checks if the incoming provider is active and has a valid status on the status endpoint."""
    import requests

    response = requests.get(STATUS_ENDPOINT, verify=False)
    response.raise_for_status()
    data = response.json()

    for node_data in data["known_nodes"]:
        if node_data["staker_address"].lower() == incoming_provider.lower():
            url = node_data["rest_url"]
            # let's ping the node's REST endpoint to check if it's active
            try:
                node_status_page = f"https://{url}/status/?json=true"
                node_response = requests.get(node_status_page, verify=False)
                node_response.raise_for_status()
                node_status_data = node_response.json()

                version = node_status_data["version"]
                if version.startswith("7.7") or version.startswith("7.6.1"):
                    return True
                else:
                    click.echo(
                        f"Incoming provider {incoming_provider} is running an incompatible version: {version}."
                    )
                    return False

            except requests.RequestException as e:
                click.echo(f"Error occurred while checking node status: {e}")
                return False

    else:
        click.echo(f"Incoming provider {incoming_provider} is not active.")
        return False
    

@click.command(cls=ConnectedProviderCommand, name="request-handover")
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
    "--incoming-provider",
    "-ip",
    help="The ethereum address of the incoming staking provider.",
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
    incoming_provider,
    auto,
):
    """Request a handover."""

    # Setup
    check_plugins()
    click.echo(f"Connected to {network.name} network.")

    # Check if incoming provider is active and has a valid status
    if not check_incoming_provider(incoming_provider):
        click.echo("Incoming provider is not active or has an invalid status. Aborting.")
        return

    # Get the contracts from the registry
    coordinator_contract = registry.get_contract(domain=domain, contract_name="Coordinator")

    # Issue handover request
    click.echo(
        f"Requesting handover for ritual {ritual_id} from "
        f"{departing_provider} to {incoming_provider}..."
    )
    transactor = Transactor(account=account, autosign=auto)
    transactor.transact(
        coordinator_contract.handoverRequest,
        ritual_id,
        departing_provider,
        incoming_provider,
    )


if __name__ == "__main__":
    cli()
