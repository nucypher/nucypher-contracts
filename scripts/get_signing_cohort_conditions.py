#!/usr/bin/python3
import json

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import (
    SUPPORTED_TACO_DOMAINS, TESTNET_PROVIDERS,
)
from deployment.params import Transactor


@click.command(cls=ConnectedProviderCommand, name="get-cohort-conditions")
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
def cli(
        domain,
        network,
        cohort_id,
        chain_id,
):

    if domain not in TESTNET_PROVIDERS:
        raise click.ClickException(f"Unsupported domain: {domain}. Supported domains are: {', '.join(TESTNET_PROVIDERS)}")

    print(f"Getting conditions for cohort {cohort_id} on {domain}:{network} with chain ID {chain_id}")

    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    print("Getting conditions...")
    print(f"Cohort ID: {cohort_id}, Chain ID: {chain_id}")
    result = signing_coordinator.getSigningCohortConditions(cohort_id, chain_id)

    print("Cohort Conditions:")
    print(json.dumps(json.loads(result), indent=4))
