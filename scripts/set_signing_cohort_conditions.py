#!/usr/bin/python3
import json

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS, TESTNET_PROVIDERS
from deployment.params import Transactor


@click.command(cls=ConnectedProviderCommand, name="set-cohort-conditions")
@account_option()
@network_option(required=True)
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option(
    "--cohort-id",
    "-cid",
    help="The cohort ID to set conditions on.",
    type=int,
    required=True,
)
@click.option(
    "--chain-id",
    "-c",
    help="The chain ID of the network where the cohort is being initiated.",
    type=int,
    required=True,
)
@click.option(
    "--auto",
    help="Automatically sign transactions.",
    is_flag=True,
)
@click.option(
    "--condition-file",
    "-cf",
    help="Path to a JSON file containing the condition to be signed.",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=False,
)
def cli(
    domain,
    account,
    network,
    auto,
    cohort_id,
    chain_id,
    condition_file,
):
    """
    Example:

    ape run set_signing_cohort_conditions --condition-file condition.json -cid 2 -c 84532
      --account lynx-deployer --domain lynx --network ethereum:sepolia:infura
    """

    with open(condition_file, "r") as file:
        condition_file_data = file.read().strip()
    if not condition_file_data:
        raise click.ClickException("Condition file is empty or not provided.")

    condition = json.loads(condition_file_data)

    if domain not in TESTNET_PROVIDERS:
        raise click.ClickException(
            f"Unsupported domain: {domain}. Supported domains are: {', '.join(TESTNET_PROVIDERS)}"
        )

    print(
        f"Setting conditions for cohort {cohort_id} on {domain}:{network} with chain ID {chain_id}"
    )

    transactor = Transactor(account=account, autosign=auto)
    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    print("Setting conditions...")
    print(f"Cohort ID: {cohort_id}, Chain ID: {chain_id}")
    print(f"Condition: {json.dumps(condition, indent=2)}")  # pretty print condition

    # compact conversion to bytes
    condition_bytes = json.dumps(condition).encode("utf-8")
    result = transactor.transact(
        signing_coordinator.setSigningCohortConditions,
        cohort_id,
        chain_id,
        condition_bytes,
    )

    print(f"Conditions set successfully: {result.transaction_hash.hex()}")
