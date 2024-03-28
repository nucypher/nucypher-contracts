import time
from datetime import datetime
from enum import IntEnum

import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option

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

END_STATES = [
    RitualState.DKG_TIMEOUT,
    RitualState.DKG_INVALID,
    RitualState.ACTIVE,
    RitualState.EXPIRED,
]

# expired means that it was active at some point in the past
SUCCESSFUL_END_STATES = [RitualState.ACTIVE, RitualState.EXPIRED]


def print_ritual_state(ritual_id, coordinator) -> RitualState:
    ritual_state = coordinator.getRitualState(ritual_id)
    print()
    print("Ritual State")
    print("============")
    print(f"\tState            : {RitualState(ritual_state).name}")

    if ritual_state in SUCCESSFUL_END_STATES:
        return ritual_state

    # if not successful, better understand why
    # OR if still ongoing, provide information
    ritual = coordinator.rituals(ritual_id)
    participants = coordinator.getParticipants(ritual_id)

    if ritual.totalTranscripts < len(participants):
        print("\t(!) Missing transcripts")
        for participant in participants:
            if not participant.transcript:
                print(f"\t\t{participant.provider}")
    elif ritual.totalAggregations < len(participants):
        print("\t(!) Missing aggregated transcripts")
        for participant in participants:
            if not participant.aggregated:
                print(f"\t\t{participant.provider}")

    return ritual_state


@click.command(cls=ConnectedProviderCommand)
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
    "--realtime/--no-realtime",
    help="Perform real-time monitoring of ritual if still ongoing",
    required=False,
    default=None,
)
def cli(network, domain, ritual_id, realtime):
    """Check/Monitor the state of a Ritual."""
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

    participants = coordinator.getParticipants(ritual_id)

    #
    # Info
    #
    print("Ritual Information")
    print("==================")
    print(f"\tThreshold         : {ritual.threshold}-of-{ritual.dkgSize}")
    print(f"\tInit Timestamp    : {datetime.fromtimestamp(ritual.initTimestamp).isoformat()}")
    print(f"\tEnd Timestamp     : {datetime.fromtimestamp(ritual.endTimestamp).isoformat()}")
    print(f"\tInitiator         : {ritual.initiator}")
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

    #
    # State
    #
    ritual_state = print_ritual_state(ritual_id, coordinator)
    if ritual_state in END_STATES or realtime is False:
        return
    elif realtime is None:
        click.confirm("Monitor DKG ritual in real-time?", abort=True)

    while ritual_state not in END_STATES:
        print()
        print("---- Waiting 15s -----")
        time.sleep(15)
        ritual_state = print_ritual_state(ritual_id, coordinator)


if __name__ == "__main__":
    cli()
