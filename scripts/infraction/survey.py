from collections import Counter, defaultdict
from enum import IntEnum
from datetime import datetime, timedelta

import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.registry import contracts_from_registry
from deployment.utils import registry_filepath_from_domain


class RitualState(IntEnum):
    NON_INITIATED = 0
    DKG_AWAITING_TRANSCRIPTS = 1
    DKG_AWAITING_AGGREGATIONS = 2
    DKG_TIMEOUT = 3
    DKG_INVALID = 4
    ACTIVE = 5
    EXPIRED = 6


END_STATES = [RitualState.DKG_TIMEOUT, RitualState.DKG_INVALID, RitualState.ACTIVE, RitualState.EXPIRED]
SUCCESSFUL_END_STATES = [RitualState.ACTIVE, RitualState.EXPIRED]
PENALTY_PERIOD = timedelta(days=90)


def collect_offenses(coordinator, from_ritual, last_ritual_id):
    provider_offenses = defaultdict(list)
    for ritual_id in range(from_ritual, last_ritual_id):
        ritual_state = coordinator.getRitualState(ritual_id)
        if ritual_state in SUCCESSFUL_END_STATES:
            continue

        ritual = coordinator.rituals(ritual_id)
        ritual_timestamp = datetime.fromtimestamp(ritual.initTimestamp)
        participants = coordinator.getParticipants(ritual_id)
        missing_transcripts = len(participants) - ritual.totalTranscripts
        missing_aggregates = len(participants) - ritual.totalAggregations

        if missing_transcripts or missing_aggregates:
            issue = 'transcripts' if missing_transcripts else 'aggregates'
            for participant in participants:
                if not participant.transcript:
                    provider_offenses[participant.provider].append(ritual_timestamp)
                    print(f"Ritual {ritual_id}: {participant.provider} missing {issue}")
    return provider_offenses


def calculate_penalty_periods(offense_timestamps):
    if not offense_timestamps:
        return []

    offense_timestamps = sorted(offense_timestamps)
    penalty_periods = []
    current_period_start = offense_timestamps[0]
    current_period_end = current_period_start + PENALTY_PERIOD

    for offense_date in offense_timestamps[1:]:
        if offense_date > current_period_end:
            penalty_periods.append((current_period_start, current_period_end))
            current_period_start = offense_date
            current_period_end = offense_date + PENALTY_PERIOD
        else:
            current_period_end = max(current_period_end, offense_date + PENALTY_PERIOD)

    penalty_periods.append((current_period_start, current_period_end))
    return penalty_periods


def apply_penalties(offense_count):
    if offense_count == 1:
        return "30% withholding for 3 months"
    elif offense_count == 2:
        return "60% withholding for 3 months"
    elif offense_count == 3:
        return "90% withholding for 3 months"
    elif offense_count >= 4:
        return "Slashing (TBD)"
    return "No penalty"


# Function to log penalties
def log_penalties(provider, offense_timestamps, penalty_periods):
    offense_count = len(offense_timestamps)
    penalty_message = apply_penalties(offense_count)
    print(f"\t{provider}: {offense_count} offenses, {len(penalty_periods)} penalty periods, Penalty: {penalty_message}")
    # for i, period in enumerate(penalty_periods, start=1):
    #     duration = (period[1] - period[0]).days
    #     print(f"\t\tPenalty Period {i}: {duration} days")


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

    provider_offenses = collect_offenses(coordinator, from_ritual, last_ritual_id)

    print(f"Total rituals: {last_ritual_id - from_ritual}")
    print("Provider Offense Count and Penalties")
    for provider, offense_timestamps in provider_offenses.items():
        penalty_periods = calculate_penalty_periods(offense_timestamps)
        log_penalties(provider, offense_timestamps, penalty_periods)


if __name__ == "__main__":
    cli()
