#!/usr/bin/python3


import json
from enum import IntEnum

import click
from ape.cli import ConnectedProviderCommand, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS


class RitualState(IntEnum):
    NON_INITIATED = 0
    DKG_AWAITING_TRANSCRIPTS = 1
    DKG_AWAITING_AGGREGATIONS = 2
    DKG_TIMEOUT = 3
    DKG_INVALID = 4
    ACTIVE = 5
    EXPIRED = 6


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
@click.option(
    "--report-infractions",
    help="Report infractions to the InfractionCollector.",
    is_flag=True,
    default=False,
)
def cli(domain, artifact, report_infractions):
    """Evaluate the heartbeat artifact."""

    # setup
    artifact_data = json.load(artifact)
    click.echo(json.dumps(artifact_data, indent=4))
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")

    # TODO: Uncomment the following lines after the InfractionCollector contract is merged.
    # infraction_collector = registry.get_contract(domain=domain, contract_name="InfractionCollector")

    # capture ritual states
    for ritual_id, cohort in artifact_data.items():

        ritual_status = coordinator.getRitualState(ritual_id)
        if ritual_status == RitualState.ACTIVE.value:
            print(f"Ritual {ritual_id} is ACTIVE.")
            continue

        elif ritual_status == RitualState.DKG_TIMEOUT.value:
            print(f"Ritual {ritual_id} status is TIMEOUT.")
            offenders = []
            participants = coordinator.getParticipants(ritual_id).call()
            for participant_info in participants:
                address, aggregated, transcript, *data = participant_info
                if not aggregated:
                    print(f"Participant {address} has not aggregated.")
                    # TODO: Missing aggregation is not yet a reportable violation.
                if not transcript:
                    print(f"Participant {address} has not submitted a transcript.")
                    offenders.append(address)

            # TODO: Uncomment the following lines after the InfractionCollector contract is merged.
            # report infractions
            # if report_infractions:
            #     receipt = infraction_collector.reportMissingTranscript(ritual_id, offenders)

            if offenders:
                print(f"{len(offenders)} ritual #{ritual_id} offenders: {offenders}")
                json.dumps(offenders)
                with open(f"ritual-{ritual_id}-offenders.json", "w") as f:
                    f.write(json.dumps(offenders))

        else:
            print(f"Ritual {ritual_id} status is {ritual_status}.")
            continue
