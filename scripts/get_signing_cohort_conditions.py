#!/usr/bin/python3
import json

import click
from ape.cli import ConnectedProviderCommand, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS


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

    print(f"Getting conditions for cohort {cohort_id} on {domain}:{network} with chain ID {chain_id}")

    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    result = signing_coordinator.getSigningCohortConditions(cohort_id, chain_id)

    print("Cohort Conditions:")
    print(json.dumps(json.loads(result.decode()), indent=2))
