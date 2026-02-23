#!/usr/bin/python3

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from deployment import registry
from deployment.constants import SUPPORTED_TACO_DOMAINS, TESTNET_PROVIDERS
from deployment.params import Transactor
from deployment.types import ChecksumAddress, MinInt


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
    type=MinInt(60 * 60 * 24),
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
    "--authority",
    "-a",
    help=(
        "The address of the authority with administrative permissions over the cohort. "
        "If not specified, the transacting account will be used as the authority."
    ),
    type=ChecksumAddress(),
    required=False,
)
@click.option(
    "--handpicked",
    help=(
        "The filepath of a file containing newline separated staking provider addresses "
        "that will be included in the cohort."
    ),
    type=click.File("r"),
    required=False,
)
@click.option(
    "--auto",
    help="Automatically sign transactions.",
    is_flag=True,
)
def cli(
    domain,
    account,
    network,
    duration,
    threshold,
    authority,
    chain_id,
    handpicked,
    auto,
):
    """
    Example:

    ape run form_signing_cohort -c 84532 -th 2 -t 2592000 --account lynx-deployer
       --domain lynx --network ethereum:sepolia:infura
    """
    if handpicked:
        print(f"Using handpicked providers from file: {handpicked.name}")
        providers = sorted(line.lower().strip() for line in handpicked)
        if not providers:
            raise click.ClickException(
                f"No staking providers found in the handpicked file {handpicked.name}"
            )
    elif domain in TESTNET_PROVIDERS:
        # testnet
        providers = TESTNET_PROVIDERS[domain]
    else:
        # mainnet without handpicked file (in the future we can do sampling here)
        raise click.ClickException(
            "On mainnet, you must provide a handpicked file containing staking providers."
        )

    if threshold > len(providers):
        raise click.ClickException(
            f"Threshold {threshold} cannot be greater than "
            f"the number of providers {len(providers)}."
        )

    authority = authority or account.address

    print(f"Initiating signing cohort on {domain}:{network} with account {account.address}...")
    transactor = Transactor(account=account, autosign=auto)
    signing_coordinator = registry.get_contract(domain=domain, contract_name="SigningCoordinator")

    result = transactor.transact(
        signing_coordinator.initiateSigningCohort,
        chain_id,
        authority,
        providers,
        threshold,
        duration,
    )
    print(f"Signing cohort initiated with transaction: {result.txn_hash}")
