#!/usr/bin/python3

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import click
import requests
import urllib3
from ape import chain
from ape.cli import ConnectedProviderCommand, network_option
from ape.contracts import ContractInstance
from ape.contracts.base import ContractContainer
from packaging.version import InvalidVersion, Version

from deployment import registry
from deployment.constants import (
    HEARTBEAT_ARTIFACT_FILENAME,
    NETWORK_SEEDNODE_STATUS_JSON_URI,
    SUPPORTED_TACO_DOMAINS,
    RitualState,
)

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


NODE_UPDATE_GRACE_PERIOD = timedelta(weeks=3)

# Reasons for node being an offender
UNREACHABLE = "Node is unreachable"
OUTDATED = "Node is running an outdated version"
UNRECOGNIZED_VERSION = "Unrecognized version"
MISSING_TRANSCRIPT = "Missing transcript"


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


def get_node_version(staker_address: str, network_data: Dict[str, Any]) -> str:
    # if this node is the one that provided the network data, return it directly
    if network_data.get("staker_address") == staker_address:
        return network_data.get("version", UNREACHABLE)
    else:
        nodes = network_data["known_nodes"]
        for node in nodes:
            if node.get("staker_address") == staker_address:
                rest_url = node["rest_url"]
                try:
                    node_status = requests.get(
                        f"https://{rest_url}/status/",
                        params={"json": "true"},
                        verify=False,
                        timeout=30,
                    )

                    # check for HTTP errors (4xx and 5xx)
                    node_status.raise_for_status()

                    return node_status.json().get("version", UNREACHABLE)
                except (
                    requests.ConnectionError,
                    requests.exceptions.ReadTimeout,
                    requests.HTTPError,
                ):
                    return UNREACHABLE

        return UNREACHABLE


def get_valid_versions() -> List[Version]:
    """Fetches valid versions considering the update grace period."""
    releases_url = "https://api.github.com/repos/nucypher/nucypher/releases"
    releases_response = requests.get(releases_url)
    releases_response.raise_for_status()
    releases_response = releases_response.json()

    valid_versions: List[Version] = []

    # GitHub seems to return releases in published_at-descending-order
    for i, release in enumerate(releases_response):
        version_str = release.get("tag_name")
        try:
            version = Version(version_str)
        except InvalidVersion:
            click.secho(
                f"⚠️  Failed to parse version from release {version_str}"
                + " Not semantic versioning format?",
                fg="red",
            )
            return []

        if i == 0:
            valid_versions.append(version)
        else:
            previous_release_date = datetime.fromisoformat(releases_response[i - 1]["published_at"])
            deadline = previous_release_date + NODE_UPDATE_GRACE_PERIOD
            # filter the versions that are considered valid to run
            if deadline > datetime.now(tz=timezone.utc):
                valid_versions.append(version)

    return valid_versions


def get_heartbeat_round_info(
    coordinator: ContractInstance, heartbeat_rituals: Dict[str, Any]
) -> tuple[int, str]:
    """Calculate the current heartbeat round number and month name."""

    def mondays_passed(date: datetime) -> int:
        """
        Returns the number of Mondays that have passed in the month up to the
        given date.
        """
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
    try:
        ritual_data = coordinator.rituals(ritual_id)
    except Exception as e:
        click.secho(f"⚠️ Failed to fetch ritual data for {ritual_id}: {e}", fg="red")
        raise
    ritual_start_time = datetime.fromtimestamp(ritual_data.initTimestamp, tz=timezone.utc)

    round = mondays_passed(ritual_start_time)
    month = ritual_start_time.strftime("%B")

    return round, month


def format_discord_message(
    offenders: Dict[str, Dict[str, Any]],
    heartbeat_round: int,
    month_name: str,
    latest_version: str,
) -> str:
    """Formats the offender data into a Discord message."""

    def get_ordinal_suffix(n: int) -> str:
        """Return the ordinal suffix for a number (1st, 2nd, 3rd, 4th, etc.)."""
        if 10 <= n % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return suffix

    # Separate offenders by reason
    unreachable_offenders: List[Tuple[str, str]] = []
    outdated_offenders: List[Tuple[str, str]] = []
    unknown_reasons_offenders: List[Tuple[str, str]] = []

    for address, details in offenders.items():
        operator = details.get("operator")
        reasons = details.get("reasons", [])

        if UNREACHABLE in reasons:
            unreachable_offenders.append((address, operator))
        elif OUTDATED in reasons:
            outdated_offenders.append((address, operator))
        elif UNRECOGNIZED_VERSION in reasons or MISSING_TRANSCRIPT in reasons:
            unknown_reasons_offenders.append((address, operator))
        else:
            click.secho(f"⚠️ {address} has unclassified reasons: {reasons}", fg="yellow")
            unknown_reasons_offenders.append((address, operator))

    # Sort each list by staking provider address
    unreachable_offenders = sorted(unreachable_offenders, key=lambda x: str.lower(x[0]))
    outdated_offenders = sorted(outdated_offenders, key=lambda x: str.lower(x[0]))
    unknown_reasons_offenders = sorted(unknown_reasons_offenders, key=lambda x: str.lower(x[0]))

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
    message += " a support ticket in 🙋┃support-ticket so we can help you to investigate the"
    message += " failure reason.\n\n"
    message += "Finally, a reminder that we will continue to monitor the health of the network."
    message += "Please, be sure you claimed the @Node Operator role in 🪪┃claim-role and stay tuned"
    message += " to announcements in this server since we will report on failing nodes."

    return message


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
    """
    Evaluates the heartbeat artifact and analyzes offenders.
    This script is intended to be run shortly after a DKG heartbeat timeout to
    check the reasons of the DKG failures.
    The reasons can be:
    UNREACHABLE, OUTDATED, UNRECOGNIZED_VERSION, MISSING_TRANSCRIPT
    """

    click.secho("🔍 Analyzing DKG protocol violations...", fg="cyan")

    valid_versions = get_valid_versions()
    if not valid_versions:
        click.secho("⚠️  Could not determine valid versions", fg="red")
        return

    artifact_data = json.load(artifact)
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")
    taco_application = registry.get_contract(domain=domain, contract_name="TACoChildApplication")

    heartbeat_round, month_name = get_heartbeat_round_info(coordinator, artifact_data)
    try:
        dkg_timeout_secs = coordinator.dkgTimeout()
        dkg_timeout = timedelta(seconds=dkg_timeout_secs)
    except Exception:
        click.secho("⚠️ Failed to fetch DKG timeout from coordinator", fg="red")
        return

    offenders: Dict[str, Dict[str, Any]] = defaultdict(dict)

    if heartbeat_round > 4:
        click.secho(
            f"⚠️ This is the heartbeat round #{heartbeat_round}, which exceeds"
            + " the expected maximum of 4 per month.",
            fg="yellow",
        )
        click.secho("Skipping heartbeat evaluation...", fg="yellow")
        return

    network_data = get_taco_network_data(domain)

    for ritual_id, _ in artifact_data.items():
        try:
            ritual_status = coordinator.getRitualState(ritual_id)
            participants = coordinator.getParticipants(ritual_id)
            init_timeout_timestamp, _ = coordinator.getTimestamps(ritual_id)
        except Exception as e:
            click.secho(f"⚠️ Failed to fetch ritual data for {ritual_id}: {e}", fg="red")
            return

        # let's check if we gave enough time to timeout: no rituals in progress
        init_timeout = datetime.fromtimestamp(init_timeout_timestamp, tz=timezone.utc)
        if init_timeout + dkg_timeout > datetime.now(tz=timezone.utc):
            click.secho(
                f"⚠️ The DKG ritual {ritual_id} is still within the timeout period."
                + " The evaluation was run too early?",
                fg="red",
            )
            return

        for participant_info in participants:
            address, _, transcript, _ = participant_info

            version = get_node_version(address, network_data)

            offenders[address] = {"ritual": ritual_id, "reasons": [], "version": version}

            # check if node is reachable and running a valid version
            if version == UNREACHABLE:
                offenders[address]["reasons"].append(UNREACHABLE)
                click.secho(f"Node {address} is unreachable", fg="cyan")
            else:
                try:
                    version = Version(version)
                    if version not in valid_versions:
                        offenders[address]["reasons"].append(OUTDATED)
                        click.secho(f"Node {address} is outdated: {version}", fg="cyan")

                # if version string isn't well formed (not semantic version)
                except InvalidVersion:
                    offenders[address]["reasons"].append(UNRECOGNIZED_VERSION)
                    click.secho(
                        f"⚠️ Got an invalid version for node {address}: {version}", fg="yellow"
                    )

            # Check ritual status for DKG violations
            if ritual_status == RitualState.DKG_TIMEOUT.value:
                if not transcript:
                    offenders[address]["reasons"].append(MISSING_TRANSCRIPT)
                    click.secho(f"Node {address} didn't send transcript", fg="cyan")

            # Fetch additional offender details for the report
            if offenders[address]["reasons"]:
                operator_address = get_operator(address, taco_application=taco_application)
                offenders[address]["operator"] = operator_address
                offenders[address]["eth_balance"] = get_eth_balance(operator_address)
            else:
                # Remove non-offenders
                offenders.pop(address, None)

    # Save offenders before network investigation
    with open("offenders.json", "w") as f:
        json.dump(offenders, f, indent=4)

    click.secho("📄 Offender report saved.", fg="green")

    # Print summary of offenders
    total_nodes = sum(len(nodes) for nodes in artifact_data.values())
    total_offenders = len(offenders.keys())
    unreachable_nodes = sum(
        1 for offender in offenders.values() if UNREACHABLE in offender.get("reasons", [])
    )
    outdated_nodes = sum(
        1 for offender in offenders.values() if OUTDATED in offender.get("reasons", [])
    )
    missing_transcripts = sum(
        1 for offender in offenders.values() if MISSING_TRANSCRIPT in offender.get("reasons", [])
    )

    click.secho("Offenders summary:")
    click.secho(f"  - Total nodes evaluated: {total_nodes}")
    click.secho(f"  - Total offenders: {total_offenders}")
    click.secho(f"  - Unreachable nodes: {unreachable_nodes}")
    click.secho(f"  - Outdated nodes: {outdated_nodes}")
    click.secho(f"  - Nodes with missing transcripts: {missing_transcripts}")

    # Generate and display Discord message
    latest_version = str(valid_versions[0])
    discord_message = format_discord_message(offenders, heartbeat_round, month_name, latest_version)

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
