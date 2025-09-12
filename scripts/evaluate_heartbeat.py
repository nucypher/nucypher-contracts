#!/usr/bin/python3

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import click
import requests
import urllib3
from ape import chain
from ape.cli import ConnectedProviderCommand, network_option
from ape.contracts import ContractInstance
from ape.contracts.base import ContractContainer

from deployment import registry
from deployment.constants import (
    HEARTBEAT_ARTIFACT_FILENAME,
    NETWORK_SEEDNODE_STATUS_JSON_URI,
    SUPPORTED_TACO_DOMAINS,
    RitualState,
)

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


LATEST_RELEASE_URL = "https://api.github.com/repos/nucypher/nucypher/releases/latest"


def get_eth_balance(address: str) -> float:
    """Fetches the ETH balance of a given address using eth-ape."""
    try:
        balance_wei = chain.provider.get_balance(address)
        return balance_wei / 1e18  # Convert from Wei to ETH
    except Exception as e:
        click.secho(f"⚠️ Failed to fetch balance for {address}: {e}", fg="red")
        return 0.0


def get_taco_network_data(domain) -> Dict[str, Any]:
    """Retrieves TACo network data (list of known nodes)."""
    domain_api = NETWORK_SEEDNODE_STATUS_JSON_URI.get(domain)

    try:
        response = requests.get(domain_api, params={"json": "true"}, verify=False, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        click.secho(f"⚠️ Failed to fetch TACo network data: {e}", fg="red")
        return {"known_nodes": []}  # Return an empty structure to avoid crashes


def get_operator(staker_address: str, taco_application: ContractContainer) -> str:
    """Retrieves the operator address of a staker."""
    try:
        info = taco_application.stakingProviderInfo(staker_address)
        return info.operator
    except Exception as e:
        click.secho(f"⚠️ Failed to fetch operator for {staker_address}: {e}", fg="red")
        return "Unknown"


def get_ordinal_suffix(n: int) -> str:
    """Return the ordinal suffix for a number (1st, 2nd, 3rd, 4th, etc.)."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return suffix


def get_heartbeat_round_info(
    coordinator: ContractInstance, heartbeat_rituals: Dict[str, Any]
) -> tuple[int, str]:
    """Calculate the current heartbeat round number and month name."""

    def mondays_passed(date: datetime) -> int:
        """Returns the number of Mondays that have passed in the month up to the given date."""
        first_day_of_month = date.replace(day=1)

        # find the first Monday of the month
        first_monday = first_day_of_month
        while first_monday.weekday() != 0:  # Monday = 0
            first_monday += timedelta(days=1)

        # Count Mondays up to the give date
        count = 0
        current = first_monday
        while current <= date:
            count += 1
            current += timedelta(weeks=1)
        return count

    ritual_id = list(heartbeat_rituals.keys())[0]
    ritual_data = coordinator.rituals(ritual_id)
    ritual_start_time = datetime.fromtimestamp(ritual_data.initTimestamp, tz=timezone.utc)

    round = mondays_passed(ritual_start_time)
    month = ritual_start_time.strftime("%B")

    return round, month


def format_discord_message(
    offenders: Dict[str, Dict[str, Any]],
    heartbeat_round: int,
    month_name: str,
) -> str:
    """Formats the offender data into a Discord message."""

    # Get the latest released version of nodes
    version_response = requests.get(LATEST_RELEASE_URL)
    latest_version = version_response.json().get("tag_name").strip("v")

    # Separate offenders by reason
    unreachable_offenders = []
    outdated_offenders = []
    unknown_reasons_offenders = []

    for ritual_id, offender_list in offenders.items():
        if ritual_id == "summary":  # Skip summary
            continue

        for address, details in offender_list.items():
            reasons = details.get("reasons", [])
            operator = details.get("operator", "Unknown")

            # Debug output
            click.secho(f"Processing {address}: reasons = {reasons}", fg="yellow")

            # Prioritize network investigation results over DKG violation reasons
            # If node has unknown reasons (HTTP 500), it goes to unknown reasons list
            if any("Unknown reasons" in reason for reason in reasons):
                click.secho(f"  -> Adding {address} to unknown reasons list", fg="magenta")
                unknown_reasons_offenders.append((address, operator))
            # If node is unreachable, it goes to unreachable list regardless of DKG violations
            elif "Node is unreachable" in reasons:
                click.secho(f"  -> Adding {address} to unreachable list", fg="red")
                unreachable_offenders.append((address, operator))
            # If node is outdated, it goes to outdated list regardless of DKG violations
            elif any("Old Version" in reason for reason in reasons):
                click.secho(f"  -> Adding {address} to outdated list", fg="blue")
                outdated_offenders.append((address, operator))
            # If node is reachable and up-to-date but has DKG violations, it goes to unreachable
            # list (since the DKG violations are likely due to connectivity/availability issues)
            else:
                click.secho(f"  -> Adding {address} to unreachable list (fallback)", fg="red")
                unreachable_offenders.append((address, operator))

    # Build Discord message
    message = "Dear TACo @Node Operator\n\n"
    message += f"We ran the {heartbeat_round}{get_ordinal_suffix(heartbeat_round)} DKG Heartbeat"
    message += f" Round for {month_name} period to monitor node uptime and availability.\n\n"

    if unreachable_offenders:
        message += "The following nodes did not complete the DKG heartbeat because they are not"
        message += " responding:\n\n"
        message += "```\n"
        message += "Staking provider address                   | Operator address\n"
        message += "----------------------------------------------------------------------------\n"
        for staking_provider, operator in unreachable_offenders:
            message += f"{staking_provider} | {operator}\n"
        message += "```\n\n"

    if outdated_offenders:
        message += "The following nodes did not complete the DKG heartbeat because they are running"
        message += " an outdated client version:\n\n"
        message += "```\n"
        message += "Staking provider address                   | Operator address\n"
        message += "----------------------------------------------------------------------------\n"
        for staking_provider, operator in outdated_offenders:
            message += f"{staking_provider} | {operator}\n"
        message += "```\n\n"

    if unknown_reasons_offenders:
        message += "The following nodes did not complete the DKG heartbeat due to unknown reasons"
        message += " (server errors):\n\n"
        message += "```\n"
        message += "Staking provider address                   | Operator address\n"
        message += "----------------------------------------------------------------------------\n"
        for staking_provider, operator in unknown_reasons_offenders:
            message += f"{staking_provider} | {operator}\n"
        message += "```\n\n"

    message += "If you're operating one of the nodes running an outdated client version, please"
    message += f" upgrade your node to v{latest_version} (latest)."
    message += "Otherwise if your node was unresponsive or experiencing server errors, please open"
    message += " a support ticket in 🙋┃support-ticket so we can help you to investigate the failure"
    message += " reason.\n\n"
    message += "Finally, a reminder that we will continue to monitor the health of the network."
    message += "Please, be sure you claimed the @Node Operator role in 🪪┃claim-role and stay tuned"
    message += " to announcements in this server since we will report on failing nodes."

    return message


def investigate_offender(
    offenders: Dict[str, Dict[str, Any]], network_data: Dict[str, Any]
) -> None:
    """Investigates the network status of offenders and adds a summary."""
    click.secho("\n🌐 Investigating offender network details...", fg="blue")
    reason_counter = Counter()
    unreachable_nodes = 0
    outdated_nodes = 0

    # Get the latest released version of nodes
    version_response = requests.get(LATEST_RELEASE_URL)
    latest_version = version_response.json().get("tag_name").strip("v")

    for ritual_id, offender_list in offenders.items():
        for address, details in offender_list.items():
            for node in network_data.get("known_nodes", []):
                if node.get("staker_address") == address:
                    rest_url = node.get("rest_url", "Unknown")
                    offenders[ritual_id][address]["url"] = (
                        f"https://{rest_url}/status/" if rest_url else "Unknown"
                    )

                    # Check node status
                    try:
                        node_status = requests.get(
                            f"https://{rest_url}/status/",
                            params={"json": "true"},
                            verify=False,
                            timeout=20,
                        )

                        if node_status.status_code == 500:
                            # HTTP 500 indicates server error - categorize as unknown reasons
                            offenders[ritual_id][address]["version"] = "Unknown"
                            offenders[ritual_id][address]["reasons"].append(
                                "Unknown reasons (HTTP 500)"
                            )
                        elif node_status.status_code != 200:
                            # Other non-200 status codes - treat as unreachable
                            raise requests.ConnectionError
                        else:
                            # HTTP 200 - node is reachable
                            version = node_status.json().get("version", "Unknown")
                            offenders[ritual_id][address]["version"] = version

                        if version != "Unknown" and version != latest_version:
                            offenders[ritual_id][address]["reasons"].append(
                                f"Old Version ({version})"
                            )
                            outdated_nodes += 1
                    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
                        offenders[ritual_id][address]["version"] = "Unknown"
                        offenders[ritual_id][address]["reasons"].append("Node is unreachable")
                        unreachable_nodes += 1

                    break  # Stop searching once IP is found

    # Count reasons for summary
    for ritual in offenders.values():
        for offender in ritual.values():
            for reason in offender.get("reasons", []):
                reason_counter[reason] += 1

    # Add summary section
    offenders["summary"] = {
        "total_offenders": sum(len(ritual) for ritual in offenders.values()),
        "reason_breakdown": dict(reason_counter),
        "unreachable_nodes": unreachable_nodes,
        "outdated_nodes": outdated_nodes,
    }

    # Save updated data with summary
    with open("offenders.json", "w") as f:
        json.dump(offenders, f, indent=4)

    click.secho("✅ Offender network investigation complete.", fg="green")
    click.secho("📄 Updated `offenders.json` with summary details.", fg="cyan")


@click.command(cls=ConnectedProviderCommand, name="evaluate-heartbeat")
@network_option(required=True)
@click.option(
    "--domain", "-d", help="TACo domain", type=click.Choice(SUPPORTED_TACO_DOMAINS), required=True
)
@click.option(
    "--artifact",
    help="The filepath of a heartbeat artifact file.",
    type=click.File("r"),
    default=HEARTBEAT_ARTIFACT_FILENAME,
)
@click.option(
    "--report-infractions",
    help="Report infractions to the InfractionCollector.",
    is_flag=True,
    default=False,
)
def cli(domain: str, artifact: Any, report_infractions: bool) -> None:
    """Evaluates the heartbeat artifact and analyzes offenders."""

    click.secho("🔍 Analyzing DKG protocol violations...", fg="cyan")

    artifact_data = json.load(artifact)
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")
    taco_application = registry.get_contract(domain=domain, contract_name="TACoChildApplication")
    offenders: Dict[str, Dict[str, Any]] = defaultdict(dict)

    heartbeat_round, month_name = get_heartbeat_round_info(coordinator, artifact_data)

    if heartbeat_round > 4:
        click.secho(
            f"⚠️ This is the heartbeat round #{heartbeat_round}, which exceeds the expected maximum"
            + " of 4 per month.",
        )
        click.secho("Skipping heartbeat evaluation...")
        return

    network_data = get_taco_network_data(domain)

    for ritual_id, cohort in artifact_data.items():
        ritual_status = coordinator.getRitualState(ritual_id)

        if ritual_status == RitualState.ACTIVE.value:
            continue  # Skip active rituals

        if ritual_status == RitualState.DKG_TIMEOUT.value:
            ritual = coordinator.rituals(ritual_id)
            participants = coordinator.getParticipants(ritual_id)

            # Check if all participants have submitted transcripts
            all_transcripts_submitted = all(
                participant_info[2] for participant_info in participants
            )

            for participant_info in participants:
                address, aggregated, transcript, *data = participant_info
                reasons = []

                if not transcript:
                    reasons.append("Missing transcript")
                # Only mark as offender for not aggregating if all transcripts were submitted
                if not aggregated and ritual.totalTranscripts == 1 and all_transcripts_submitted:
                    reasons.append("Did not aggregate")

                if reasons:
                    offenders[ritual_id][address] = {"reasons": reasons}
                    click.secho(
                        f"🧐 Investigating offender {address} in ritual {ritual_id}", fg="yellow"
                    )

                    # Fetch additional offender details
                    operator_address = get_operator(address, taco_application=taco_application)
                    offenders[ritual_id][address]["operator"] = operator_address
                    offenders[ritual_id][address]["eth_balance"] = get_eth_balance(operator_address)

    # Save offenders before network investigation
    with open("offenders.json", "w") as f:
        json.dump(offenders, f, indent=4)

    click.secho(
        f"📄 Offender report saved with {sum(len(o) for o in offenders.values())} offenders.",
        fg="green",
    )
    investigate_offender(offenders, network_data)

    # Generate and display Discord message
    discord_message = format_discord_message(offenders, heartbeat_round, month_name)

    click.secho("\n" + "=" * 80, fg="cyan")
    click.secho("📢 DISCORD MESSAGE (copy below):", fg="cyan")
    click.secho("=" * 80, fg="cyan")
    click.secho(discord_message, fg="white")
    click.secho("=" * 80, fg="cyan")

    # Also save to file for easy copying
    with open("discord_message.txt", "w") as f:
        f.write(discord_message)
    click.secho("💾 Discord message also saved to 'discord_message.txt'", fg="green")


if __name__ == "__main__":
    cli()
