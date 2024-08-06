#!/usr/bin/python3

import click
from ape import project
from ape.cli import ConnectedProviderCommand, account_option

from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins, registry_filepath_from_domain, sample_nodes


def validate_options(ctx):
    if "handpicked" in ctx.params and ctx.params["handpicked"]:
        if "num_nodes" in ctx.params and ctx.params["num_nodes"]:
            raise click.BadOptionUsage(
                option_name="--handpicked",
                message="Cannot specify both --num-nodes and --handpicked.",
            )
        if "random_seed" in ctx.params and ctx.params["random_seed"]:
            raise click.BadOptionUsage(
                option_name="--handpicked",
                message="Cannot specify both --random-seed and --handpicked.",
            )
    if not ctx.params.get("handpicked") and not ctx.params.get("num_nodes"):
        raise click.BadOptionUsage(
            option_name="--num-nodes", message="Must specify either --num-nodes or --handpicked."
        )


class MinInt(click.ParamType):
    name = "minint"

    def __init__(self, min_value):
        self.min_value = min_value

    def convert(self, value, param, ctx):
        try:
            ivalue = int(value)
        except ValueError:
            self.fail(f"{value} is not a valid integer", param, ctx)
        if ivalue < self.min_value:
            self.fail(
                f"{value} is less than the minimum allowed value of {self.min_value}", param, ctx
            )
        return ivalue


@click.command(cls=ConnectedProviderCommand)
@account_option()
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
    "-a",
    help="The name of an access controller contract.",
    type=click.Choice(["GlobalAllowList", "OpenAccessAuthorizer", "ManagedAllowList"]),
    required=True,
)
@click.option(
    "--fee-model",
    "-f",
    help="The name of a fee model contract.",
    type=click.Choice(["FreeFeeModel", "BqETHSubscription"]),
    required=True,
)
@click.option(
    "--num-nodes",
    help="Number of nodes to use for the ritual.",
    type=int,
    required=False,
)
@click.option("--random-seed", help="Random seed integer for sampling.", required=False, type=int)
@click.option(
    "--authority", help="The ethereum address of the ritual authority.", required=False, type=str
)
@click.option(
    "--handpicked",
    help="The filepath of a file containing newline separated staking provider addresses.",
    required=False,
    type=click.File("r"),
)
def cli(
    domain,
    duration,
    account,
    access_controller,
    fee_model,
    num_nodes,
    random_seed,
    authority,
    handpicked,
):

    ctx = click.get_current_context()
    validate_options(ctx)

    check_plugins()
    transactor = Transactor(account=account)
    registry_filepath = registry_filepath_from_domain(domain=domain)
    chain_id = project.chain_manager.chain_id
    deployments = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    coordinator = deployments[project.Coordinator.contract_type.name]

    try:
        access_controller = deployments[getattr(project, access_controller).contract_type.name]
        fee_model = deployments[getattr(project, fee_model).contract_type.name]
    except KeyError as e:
        raise ValueError(f"Contract not found in registry for domain {domain}: {e}")

    if not authority:
        authority = transactor.get_account().address
        click.confirm(f"Using {authority} as the ritual authority. Continue?", abort=True)

    if handpicked:
        providers = sorted(line.lower() for line in handpicked)
        if not providers:
            raise ValueError(f"No staking providers found in the handpicked file {handpicked.name}")
    else:
        providers = sample_nodes(
            domain=domain, num_nodes=num_nodes, duration=duration, random_seed=random_seed
        )

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
