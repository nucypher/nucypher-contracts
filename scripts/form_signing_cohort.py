#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import (
    SUPPORTED_TACO_DOMAINS, TAPIR, LYNX, TESTNET_PROVIDERS,
)
from deployment.params import Transactor
from deployment.types import MinInt


@click.command(cls=ConnectedProviderCommand, name="form-signing-cohort")
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
    help="Duration of the cohort in seconds. Must be at least 24h.",
    type=MinInt(1),
    required=True,
)
@click.option(
    "--threshold",
    "-th",
    help="The threshold number of signatures required to sign the message.",
    type=MinInt(1),
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
        duration,
        threshold,
        chain_id,
        auto,
        condition_file,
):
    """
    ape run form_signing_cohort -c 84532 -th 2 -t 84532 --account lynx-deployer --domain lynx --network ethereum:sepolia
    """
    if domain not in (LYNX, TAPIR):
        raise click.ClickException(f"Unsupported domain: {domain}. Supported domains are: {SUPPORTED_TACO_DOMAINS}")
    providers = TESTNET_PROVIDERS[domain]

    print(f"Initiating signing cohort on {domain}:{network} with account {account.address}...")
    transactor = Transactor(account=account, autosign=auto)
    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    result = transactor.transact(
        signing_coordinator.initiateSigningCohort,
        chain_id, account.address, providers, threshold, duration
    )
    print(f"Signing cohort initiated with transaction: {result.txn_hash}")
