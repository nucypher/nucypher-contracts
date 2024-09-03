from collections import Counter, defaultdict
from enum import IntEnum

import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain

# Define RitualState as an IntEnum for clarity and ease of use
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

# Define end states and successful end states
END_STATES = [
    RitualState.DKG_TIMEOUT,
    RitualState.DKG_INVALID,
    RitualState.ACTIVE,
    RitualState.EXPIRED,
]

SUCCESSFUL_END_STATES = [RitualState.ACTIVE, RitualState.EXPIRED]


def calculate_penalty(offense_count):
    """Calculate penalty percentage based on the number of offenses."""
    if offense_count == 1:
        return '30% withholding for 3 months'
    elif offense_count == 2:
        return '60% withholding for 3 months'
    elif offense_count == 3:
        return '90% withholding for 3 months'
    elif offense_count >= 4:
        return "Slashing (TBD)"
    return 0


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
    "--from-ritual",
    "-r",
    help="Ritual ID to start from",
    default=0,
    type=int,
)
def cli(network, domain, from_ritual):
    registry_filepath = registry_filepath_from_domain(domain=domain)
    contracts = contracts_from_registry(
        registry_filepath, chain_id=networks.active_provider.chain_id
    )
    coordinator = project.Coordinator.at(contracts["Coordinator"].address)
    last_ritual_id = coordinator.numberOfRituals()

    counter = Counter()
    offenders = defaultdict(list)
    provider_offense_count = defaultdict(int)

    for ritual_id in range(from_ritual, last_ritual_id - 1):
        ritual_state = coordinator.getRitualState(ritual_id)

        if ritual_state in SUCCESSFUL_END_STATES:
            counter['ok'] += 1
            print(f"Ritual ID: {ritual_id} OK")
            continue

        ritual = coordinator.rituals(ritual_id)
        participants = coordinator.getParticipants(ritual_id)
        missing_transcripts = len(participants) - ritual.totalTranscripts
        missing_aggregates = len(participants) - ritual.totalAggregations

        if missing_transcripts or missing_aggregates:
            issue = 'transcripts' if missing_transcripts else 'aggregates'
            counter[f'missing_{issue}'] += 1
            print(f"(!) Ritual {ritual_id} missing "
                  f"{missing_transcripts or missing_aggregates}/{len(participants)} {issue}")

            for participant in participants:
                if not participant.transcript:
                    offenders[ritual_id].append(participant.provider)
                    provider_offense_count[participant.provider] += 1
                    print(f"\t{participant.provider} (!) Missing transcript")

    print(f"Total rituals: {last_ritual_id - from_ritual}")
    print("Provider Offense Count and Penalties")
    for provider, count in provider_offense_count.items():
        penalty = calculate_penalty(count)
        print(f"\t{provider}: {count} offenses, Penalty: {penalty}")


if __name__ == "__main__":
    cli()
