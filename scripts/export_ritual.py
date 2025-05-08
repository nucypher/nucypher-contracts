#!/usr/bin/python3

import click
from ape import networks
from ape.cli import ConnectedProviderCommand, account_option

from deployment import registry
from deployment.constants import ACCESS_CONTROLLERS, SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor
from deployment.types import ChecksumAddress
from deployment.utils import check_plugins


@click.command(cls=ConnectedProviderCommand, name="export-rituals")
@account_option()
# @network_option(required=True)
@click.option(
    "--domain-from",
    "-df",
    help="From TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
@click.option(
    "--domain-to",
    "-dt",
    help="To TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
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
    help="The address of the fee model/subscription contract.",
    type=ChecksumAddress(),
    required=True,
)
@click.option("--ritual-id", "-r", help="Ritual ID to check", type=int, required=True)
def cli(
    domain_from,
    domain_to,
    account,
    # network,
    access_controller,
    fee_model,
    ritual_id,
):
    """Export a ritual between TACo domains."""

    # Setup
    check_plugins()
    # click.echo(f"Connected to {network.name} network.")

    # Get the contracts from the registry
    ritual = None
    participants = None
    with networks.polygon.mainnet.use_provider("infura"):
        coordinator_contract_from = registry.get_contract(
            domain=domain_from, contract_name="Coordinator"
        )
        ritual = coordinator_contract_from.rituals(ritual_id)
        participants = coordinator_contract_from.getParticipants(ritual_id)

    with networks.polygon.sepolia.use_provider("infura"):
        coordinator_contract_to = registry.get_contract(
            domain=domain_to, contract_name="Coordinator"
        )
        # access_controller_contract = registry.get_contract(
        #     domain=domain_to, contract_name=access_controller
        # )
        # fee_model_contract = Contract(fee_model)

        # Initiate the ritual
        transactor = Transactor(account=account)
        transactor.transact(
            coordinator_contract_to.importRitual,
            ritual_id,
            ritual.initiator,
            ritual.initTimestamp,
            ritual.endTimestamp,
            ritual.totalTranscripts,
            ritual.totalAggregations,
            ritual.authority,
            ritual.dkgSize,
            # ritual.threshold,
            # ritual.aggregationMismatch,
            # access_controller_contract.address,
            ritual.publicKey,
            ritual.aggregatedTranscript,
            # fee_model_contract.address,
            participants,
        )


if __name__ == "__main__":
    cli()
