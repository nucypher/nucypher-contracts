#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS
from deployment.params import Transactor


@click.command(cls=ConnectedProviderCommand)
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
    "-i",
    help="The cohort ID of the already formed cohort.",
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
def cli(
    domain,
    account,
    chain_id,
    cohort_id,
    auto,
):
    """
    Deploy a signing cohort on an additional chain for an already formed cohort.

    Example:

    ape run signing_cohort_additional_chain -d lynx -i 0 -c 84532 --network ethereum:sepolia:infura
    """
    print(
        f"Deploying signing cohort #{cohort_id} on additional chain {chain_id} "
        f"with account {account.address}..."
    )
    transactor = Transactor(account=account, autosign=auto)
    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    result = transactor.transact(
        signing_coordinator.deployAdditionalChainForSigningMultisig, chain_id, cohort_id
    )
    print(f"Signing cohort deployed on chain {chain_id} with transaction: {result.txn_hash}")
