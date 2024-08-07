#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import ACCESS_CONTROLLERS, FEE_MODELS, SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress, MinInt
from deployment.utils import check_plugins, sample_nodes


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
    required=True,
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
    help="The name of a fee model contract.",
    type=click.Choice(FEE_MODELS),
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
):
    """Initiate a ritual for a TACo domain."""

    # Setup
    check_plugins()
    click.echo(f"Connected to {network.name} network.")
    if not (bool(handpicked) ^ (num_nodes is not None)):
        raise click.BadOptionUsage(
            option_name="--num-nodes",
            message=f"Specify either --num-nodes or --handpicked; got {num_nodes} {handpicked}",
        )
    if handpicked and random_seed:
        raise click.BadOptionUsage(
            option_name="--random-seed",
            message="Cannot specify --random-seed when using --handpicked.",
        )

    # Get the staking providers in the ritual cohort
    if handpicked:
        providers = sorted(line.lower() for line in handpicked)
        if not providers:
            raise ValueError(f"No staking providers found in the handpicked file {handpicked.name}")
    else:
        providers = sample_nodes(
            domain=domain, num_nodes=num_nodes, duration=duration, random_seed=random_seed
        )

    # Get the contracts from the registry
    coordinator = registry.get_contract(domain=domain, contract_name="Coordinator")
    access_controller = registry.get_contract(domain=domain, contract_name=access_controller)
    fee_model = registry.get_contract(domain=domain, contract_name=fee_model)

    # Initiate the ritual
    transactor = Transactor(account=account)
    transactor.transact(
        coordinator.initiateRitual,
        fee_model.address,
        providers,
        authority,
        duration,
        access_controller.address,
    )


if __name__ == "__main__":
    cli()
