import click
from eth_typing import ChecksumAddress

from deployment.constants import (
    ACCESS_CONTROLLERS,
    SUPPORTED_TACO_DOMAINS
)


access_controller_option = click.option(
    "--access-controller",
    "-a",
    help="global allow list or open access authorizer.",
    type=click.Choice(ACCESS_CONTROLLERS),
    required=True,
)

domain_option = click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)

ritual_id_option = click.option(
    "--ritual-id",
    "-r",
    help="ID of the ritual",
    required=True,
    type=int
)

subscription_contract_option = click.option(
    "--subscription-contract",
    "-s",
    help="Name of a subscription contract",
    type=click.Choice(["BqETHSubscription"]),
    required=True,
)

encryptor_slots_option = click.option(
    "--encryptor-slots",
    "-es",
    help="Number of encryptor slots to pay for.",
    required=True,
    type=int
)

encryptors_option = click.option(
    "--encryptors",
    "-e",
    help="List of encryptor addresses to remove.",
    multiple=True,
    required=True,
    type=ChecksumAddress
)
