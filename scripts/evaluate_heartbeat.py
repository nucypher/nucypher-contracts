#!/usr/bin/python3


import json

import click
from ape.cli import ConnectedProviderCommand, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS


@click.command(cls=ConnectedProviderCommand, name="evaluate-heartbeat")
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option(
    "--artifact",
    help="The filepath of a heartbeat artifact file.",
    type=click.File("r"),
)
def cli(domain, artifact):
    """Evaluate the heartbeat artifact."""
    artifact_data = json.load(artifact)
    click.echo(json.dumps(artifact_data, indent=4))
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")

    for ritual_id, cohort in artifact_data.items():
        ritual_status = coordinator.getRitualState(ritual_id)
        if ritual_status == 5:
            print(f"Ritual {ritual_id} is ACTIVE.")
            continue

        print(f"Ritual {ritual_id} is in a bad state.")

        offenders = []
        participants = coordinator.getParticipants(ritual_id).call()
        for participant in participants:
            participant_address = participant[0]
            participant_aggregated = participant[1]
            participant_transcript = participant[2]
            if not participant_aggregated:
                print(f"Participant {participant_address} has not aggregated.")
                offenders.append(participant_address)
            if not participant_transcript:
                print(f"Participant {participant_address} has not submitted a transcript.")
                offenders.append(participant_address)

        print(f"Identified {len(offenders)} offenders: {offenders}")
