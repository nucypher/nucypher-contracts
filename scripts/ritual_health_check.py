from datetime import datetime
from enum import IntEnum

import click
from ape import networks, project
from ape.cli import NetworkBoundCommand, network_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain

RitualState = IntEnum(
    "RitualState",
    [
        "NON_INITIATED",
        "DKG_AWAITING_TRANSCRIPTS",
        "DKG_AWAITING_AGGREGATIONS",
        "DKG_TIMEOUT",
        "DKG_INVALID",
        "ACTIVE",
        "EXPIRED",
    ],
    start=0,
)


@click.command(cls=NetworkBoundCommand)
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option("--ritual-id", "-r", help="Ritual ID to check", type=int, required=True)
def cli(network, domain, ritual_id):
    """Verify deployed contracts from a registry file."""
    registry_filepath = registry_filepath_from_domain(domain=domain)
    contracts = contracts_from_registry(
        registry_filepath, chain_id=networks.active_provider.chain_id
    )

    taco_child_application = project.TACoChildApplication.at(
        contracts["TACoChildApplication"].address
    )
    coordinator = project.Coordinator.at(contracts["Coordinator"].address)
    try:
        ritual = coordinator.rituals(ritual_id)
    except Exception:
        print(f"x Ritual ID #{ritual_id} not found")
        raise click.Abort()

    ritual_state = coordinator.getRitualState(ritual_id)
    participants = coordinator.getParticipants(ritual_id)

    # Info
    print("Ritual Information")
    print("==================")
    print(f"\tInitiator         : {ritual.initiator}")
    print(f"\tInit Timestamp    : {datetime.fromtimestamp(ritual.initTimestamp).isoformat()}")
    print(f"\tEnd Timestamp     : {datetime.fromtimestamp(ritual.endTimestamp).isoformat()}")
    print(f"\tAuthority         : {ritual.authority}")
    isGlobalAllowList = ritual.accessController == contracts["GlobalAllowList"].address
    print(
        f"\tAccessController  : "
        f"{ritual.accessController} {'(GlobalAllowList)' if isGlobalAllowList else ''}"
    )
    print("\tParticipants      :")
    for participant in participants:
        provider = participant.provider
        staking_provider_info = taco_child_application.stakingProviderInfo(provider)
        print(f"\t\t{provider} (operator={staking_provider_info.operator})")

    print()
    print("Ritual State")
    print("============")
    print(f"\tState             : {RitualState(ritual_state).name}")
    if ritual_state == RitualState.DKG_AWAITING_TRANSCRIPTS:
        if ritual.totalTranscripts < len(participants):
            print("\t! Missing transcripts")
            for participant in participants:
                if not participant.transcript:
                    print(f"\t\t{participant.provider}")
    elif ritual_state == RitualState.DKG_AWAITING_AGGREGATIONS:
        if ritual.totalAggregations < len(participants):
            print("\t! Missing aggregated transcripts")
            for participant in participants:
                if not participant.aggregated:
                    print(f"\t\t{participant.provider}")


if __name__ == "__main__":
    cli()
