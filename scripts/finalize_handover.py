#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option
from nucypher_core.ferveo import AggregatedTranscript, HandoverTranscript

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress
from deployment.utils import check_plugins


def validate_handover_data(coordinator, ritual_id, departing_provider):
    """Validate the handover data for the ritual."""
    handover_key = coordinator.getHandoverKey(ritual_id, departing_provider)
    handover = coordinator.handovers(handover_key)
    assert (
        HandoverTranscript.from_bytes(handover.transcript) is not None
    ), "Handover transcript should be valid"

    ritual = coordinator.rituals(ritual_id)
    existing_aggregated_transcript = ritual.aggregatedTranscript

    # find the share index of the departing provider
    # FIXME: See ferveo#210 - should be probably be included in the handover data
    participants = coordinator.getParticipants(ritual_id, 0, 0, False)
    share_index = -1
    for index, participant in enumerate(participants):
        if participant.provider == departing_provider:
            share_index = index
            break
    assert share_index != -1, "Departing validator should be in the ritual providers list"

    # create the new aggregate transcript by replacing the departing provider's share
    blinded_share_position = coordinator.blindedSharePosition(share_index, ritual.threshold)
    g2point_size = 96  # G2Point size

    blinded_share = handover.blindedShare
    assert len(blinded_share) == g2point_size, "Blinded share should be of size G2Point"

    new_aggregate_transcript = (
        existing_aggregated_transcript[:blinded_share_position]
        + blinded_share
        + existing_aggregated_transcript[blinded_share_position + g2point_size :]
    )

    # ensure that thew new aggregate transcript is valid
    # FIXME: See ferveo#209 - this should be done in ferveo
    public_key_metadata = b"0\x00\x00\x00\x00\x00\x00\x00"
    public_key = ritual.publicKey
    transcript = (
        bytes(new_aggregate_transcript) + public_key_metadata + (public_key[0] + public_key[1])
    )
    assert (
        AggregatedTranscript.from_bytes(transcript) is not None
    ), "New aggregate transcript should be valid"


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
    coordinator_contract = registry.get_contract(domain=domain, contract_name="HandoverCoordinator")

    # Validate the handover data
    click.echo(
        f"Validating handover data for ritual {ritual_id} "
        f"and departing provider {departing_provider}..."
    )
    validate_handover_data(coordinator_contract, ritual_id, departing_provider)
    click.echo("Handover data validated successfully.")

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
