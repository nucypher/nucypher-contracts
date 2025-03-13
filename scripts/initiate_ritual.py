#!/usr/bin/python3
import json
import os
import time

import click
from ape import Contract, chain
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import ACCESS_CONTROLLERS, SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress, MinInt
from deployment.utils import check_plugins, sample_nodes, get_heartbeat_cohorts


@click.command(cls=ConnectedProviderCommand, name="initiate-ritual")
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
    "--duration",
    "-t",
    help="Duration of the ritual in seconds. Must be at least 24h.",
    type=MinInt(86400),
    required=False,
)
@click.option(
    "--access-controller",
    "-c",
    help="The registry name of an access controller contract.",
    type=click.Choice(ACCESS_CONTROLLERS),
    required=True,
)
@click.option(
    "--fee-model",
    "-f",
    help="The address of the fee model/subscription contract.",
    type=ChecksumAddress(),
    required=True,
)
@click.option(
    "--authority",
    "-a",
    help="The ethereum address of the ritual authority.",
    required=True,
    type=ChecksumAddress(),
)
@click.option(
    "--min-version",
    "-mv",
    help="Minimum version to sample",
    type=str,
)
@click.option(
    "--num-nodes",
    "-n",
    help="Number of nodes to use for the ritual.",
    type=int,
)
@click.option(
    "--random-seed",
    "-r",
    help="Random seed integer for bucket sampling on mainnet.",
    type=int,
)
@click.option(
    "--handpicked",
    help="The filepath of a file containing newline separated staking provider addresses.",
    type=click.File("r"),
)
@click.option(
    "--autosign",
    is_flag=True,
)
@click.option(
    "--heartbeat",
    is_flag=True,
)
def cli(
    domain,
    account,
    network,
    duration,
    access_controller,
    fee_model,
    authority,
    num_nodes,
    random_seed,
    handpicked,
    min_version,
    autosign,
    heartbeat,
):
    """Initiate a ritual for a TACo domain."""

    # Setup
    check_plugins()
    click.echo(f"Connected to {network.name} network.")
    if not heartbeat and not (bool(handpicked) ^ (num_nodes is not None)):
        raise click.BadOptionUsage(
            option_name="--num-nodes",
            message=f"Specify either --num-nodes or --handpicked; got {num_nodes}, {handpicked}.",
        )
    if handpicked and random_seed:
        raise click.BadOptionUsage(
            option_name="--random-seed",
            message="Cannot specify --random-seed when using --handpicked.",
        )
    if handpicked and min_version:
        raise click.BadOptionUsage(
            option_name="--min-version",
            message="Cannot specify --min-version when using --handpicked.",
        )
    if heartbeat and (handpicked or num_nodes or random_seed or min_version):
        raise click.BadOptionUsage(
            option_name="--heartbeat",
            message="Cannot specify --heartbeat with any other sampling options.",
        )

    # Get the contracts from the registry
    coordinator_contract = registry.get_contract(domain=domain, contract_name="Coordinator")
    access_controller_contract = registry.get_contract(
        domain=domain, contract_name=access_controller
    )
    fee_model_contract = Contract(fee_model)

    # if using a subscription, duration needs to be calculated
    if fee_model_contract.contract_type.name == "StandardSubscription":
        start_of_subscription = fee_model_contract.startOfSubscription()
        duration = (
            fee_model_contract.subscriptionPeriodDuration()
            + fee_model_contract.yellowPeriodDuration()
            + fee_model_contract.redPeriodDuration()
        )
        if start_of_subscription > 0:
            end_of_subscription = fee_model_contract.getEndOfSubscription()
            now = chain.blocks.head.timestamp
            if now > end_of_subscription:
                raise ValueError("Subscription has already ended.")
            click.echo(
                "Subscription has already started. Subtracting the elapsed time from the duration."
            )
            elapsed = now - start_of_subscription + 100
            duration -= elapsed

    # Get the staking providers in the ritual cohort
    if heartbeat:
        taco_application = registry.get_contract(domain=domain, contract_name="TACoChildApplication")
        cohorts = get_heartbeat_cohorts(taco_application=taco_application)
        duration = 86400  # default to 24h
    else:
        if handpicked:
            cohort = sorted(line.lower().strip() for line in handpicked)
            if not cohort:
                raise ValueError(f"No staking providers found in the handpicked file {handpicked.name}")
        else:
            cohort = sample_nodes(
                domain=domain,
                num_nodes=num_nodes,
                duration=duration,
                random_seed=random_seed,
                min_version=min_version,
            )
        cohorts = [cohort]

    rituals = {}
    for cohort in cohorts:
        # TODO: Failure recovery? (not enough funds, outages, etc.)
        # Initiate the ritual(s)
        transactor = Transactor(account=account, autosign=autosign)
        result = transactor.transact(
            coordinator_contract.initiateRitual,
            fee_model_contract.address,
            cohort,
            authority,
            duration,
            access_controller_contract.address,
        )

        ritual_id = result.events[0].ritualId
        rituals[ritual_id] = cohort
        time.sleep(1)  # chill for a sec

    # Save the ritual data
    if heartbeat:
        # remove the file if it exists
        try:
            os.remove("rituals.json")
        except OSError:
            pass
        json.dumps(rituals, indent=4)
        with open("rituals.json", "w") as f:
            f.write(json.dumps(rituals, indent=4))


if __name__ == "__main__":
    cli()
