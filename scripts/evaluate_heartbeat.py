#!/usr/bin/python3

import json
import requests
import urllib3
from collections import defaultdict, Counter
from enum import IntEnum
from typing import Dict, Any

from ape import chain
import click
from ape.cli import ConnectedProviderCommand, network_option
from ape.contracts.base import ContractContainer

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS, HEARTBEAT_ARTIFACT_FILENAME

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RitualState(IntEnum):
    """Represents the different states of a DKG ritual."""
    NON_INITIATED = 0
    DKG_AWAITING_TRANSCRIPTS = 1
    DKG_AWAITING_AGGREGATIONS = 2
    DKG_TIMEOUT = 3
    DKG_INVALID = 4
    ACTIVE = 5
    EXPIRED = 6


NUCYPHER_MAINNET_API = "https://mainnet.nucypher.network:9151/status/?json=true"
LATEST_NUCYPHER_VERSION = "7.4.1"


def get_eth_balance(address: str) -> float:
    """Fetches the ETH balance of a given address using eth-ape."""
    try:
        balance_wei = chain.provider.get_balance(address)
        return balance_wei / 1e18  # Convert from Wei to ETH
    except Exception as e:
        click.secho(f"⚠️ Failed to fetch balance for {address}: {e}", fg="red")
        return 0.0


def get_nucypher_network_data() -> Dict[str, Any]:
    """Retrieves NuCypher network data (list of known nodes)."""
    try:
        response = requests.get(NUCYPHER_MAINNET_API, params={"json": "true"}, verify=False, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        click.secho(f"⚠️ Failed to fetch NuCypher network data: {e}", fg="red")
        return {"known_nodes": []}  # Return an empty structure to avoid crashes


def get_operator(staker_address: str, taco_application: ContractContainer) -> str:
    """Retrieves the operator address of a staker."""
    try:
        info = taco_application.stakingProviderInfo(staker_address)
        return info.operator
    except Exception as e:
        click.secho(f"⚠️ Failed to fetch operator for {staker_address}: {e}", fg="red")
        return "Unknown"


def investigate_offender_networks(offenders: Dict[str, Dict[str, Any]], network_data: Dict[str, Any]) -> None:
    """Investigates the network status of offenders and adds a summary."""
    click.secho("\n🌐 Investigating offender network details...", fg="blue")
    reason_counter = Counter()
    unreachable_nodes = 0
    outdated_nodes = 0

    for ritual_id, offender_list in offenders.items():
        for address, details in offender_list.items():
            for node in network_data.get("known_nodes", []):
                if node.get("staker_address") == address:
                    rest_url = node.get("rest_url", "Unknown")
                    offenders[ritual_id][address]["url"] = f"https://{rest_url}/status/" if rest_url else "Unknown"

                    # Check node status
                    try:
                        node_status = requests.get(f"https://{rest_url}/status/", params={"json": "true"}, verify=False,
                                                   timeout=20)
                        version = node_status.json().get("version", "Unknown")
                        offenders[ritual_id][address]["version"] = version

                        if version != "Unknown" and version != LATEST_NUCYPHER_VERSION:
                            offenders[ritual_id][address]["reasons"].append(f"Old Version ({version})")
                            outdated_nodes += 1
                    except requests.ConnectionError:
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
@click.option("--domain", "-d", help="TACo domain", type=click.Choice(SUPPORTED_TACO_DOMAINS), required=True)
@click.option("--artifact", help="The filepath of a heartbeat artifact file.", type=click.File("r"),
              default=HEARTBEAT_ARTIFACT_FILENAME)
@click.option("--report-infractions", help="Report infractions to the InfractionCollector.", is_flag=True,
              default=False)
def cli(domain: str, artifact: Any, report_infractions: bool) -> None:
    """Evaluates the heartbeat artifact and analyzes offenders."""

    click.secho("🔍 Analyzing DKG protocol violations...", fg="cyan")

    artifact_data = json.load(artifact)
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")
    taco_application = registry.get_contract(domain=domain, contract_name="TACoChildApplication")
    offenders: Dict[str, Dict[str, Any]] = defaultdict(dict)

    # Load NuCypher network data
    network_data = get_nucypher_network_data()

    for ritual_id, cohort in artifact_data.items():
        ritual_status = coordinator.getRitualState(ritual_id)

        if ritual_status == RitualState.ACTIVE.value:
            continue  # Skip active rituals

        if ritual_status == RitualState.DKG_TIMEOUT.value:
            ritual = coordinator.rituals(ritual_id)
            participants = coordinator.getParticipants(ritual_id)

            for participant_info in participants:
                address, aggregated, transcript, *data = participant_info
                reasons = []

                if not transcript:
                    reasons.append("Missing transcript")
                if not aggregated and ritual.totalTranscripts == 1:
                    reasons.append("Did not aggregate")

                if reasons:
                    offenders[ritual_id][address] = {"reasons": reasons}
                    click.secho(f"🧐 Investigating offender {address} in ritual {ritual_id}", fg="yellow")

                    # Fetch additional offender details
                    operator_address = get_operator(address, taco_application=taco_application)
                    offenders[ritual_id][address]["operator"] = operator_address
                    offenders[ritual_id][address]["eth_balance"] = get_eth_balance(operator_address)

    # Save offenders before network investigation
    with open("offenders.json", "w") as f:
        json.dump(offenders, f, indent=4)

    click.secho(f"📄 Offender report saved with {sum(len(o) for o in offenders.values())} offenders.", fg="green")
    investigate_offender_networks(offenders, network_data)


if __name__ == "__main__":
    cli()
