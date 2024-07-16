import json
import os
import click

import requests
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

# Load environment variables
load_dotenv()
PROVIDER_URL = os.environ.get("PROVIDER_URL")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

MAX_NODES = 10
NUCYPHER_DOMAIN = "lynx"
CHAIN = "80002"
PORTER_ENDPOINT = f"https://porter-{NUCYPHER_DOMAIN}.nucypher.community"

with open(f"deployment/artifacts/{NUCYPHER_DOMAIN}.json", "r") as f:
    registry = json.load(f)

SUBSCRIPTION_CONTRACT_ADDRESS = registry[CHAIN]["BqETHSubscription"]["address"]
SUBSCRIPTION_CONTRACT_ABI = registry[CHAIN]["BqETHSubscription"]["abi"]
ERC20_CONTRACT_ADDRESS = registry[CHAIN][NUCYPHER_DOMAIN.title() + "RitualToken"]["address"]
ERC20_CONTRACT_ABI = registry[CHAIN][NUCYPHER_DOMAIN.title() + "RitualToken"]["abi"]
COORDINATOR_CONTRACT_ADDRESS = registry[CHAIN]["Coordinator"]["address"]
COORDINATOR_CONTRACT_ABI = registry[CHAIN]["Coordinator"]["abi"]
GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS = registry[CHAIN]["GlobalAllowList"]["address"]
GLOBAL_ALLOW_LIST_CONTRACT_ABI = registry[CHAIN]["GlobalAllowList"]["abi"]


def setup_connections():
    """Set up Web3 connections."""
    w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    account = w3.eth.account.from_key(PRIVATE_KEY)
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    return w3, account


def setup_contracts():
    """Set up contract instances."""
    w3, _ = setup_connections()
    erc20_contract = w3.eth.contract(address=ERC20_CONTRACT_ADDRESS, abi=ERC20_CONTRACT_ABI)
    subscription_contract = w3.eth.contract(address=SUBSCRIPTION_CONTRACT_ADDRESS, abi=SUBSCRIPTION_CONTRACT_ABI)
    coordinator_contract = w3.eth.contract(address=COORDINATOR_CONTRACT_ADDRESS, abi=COORDINATOR_CONTRACT_ABI)
    global_allow_list_contract = w3.eth.contract(address=GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS, abi=GLOBAL_ALLOW_LIST_CONTRACT_ABI)
    click.echo(f"ERC20 contract: {erc20_contract.address}")
    click.echo(f"Subscription contract: {subscription_contract.address}")
    click.echo(f"Coordinator contract: {coordinator_contract.address}")
    click.echo(f"Global allow list contract: {global_allow_list_contract.address}")
    return erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract


@click.group()
def cli():
    """BqETH Subscription CLI"""
    pass


@cli.command()
@click.option('--encryptor-slots', default=2, help='Number of encryptor slots to pay for.')
def pay_subscription(encryptor_slots):
    """Pay for a new subscription period and initial encryptor slots."""
    w3, account = setup_connections()
    erc20_contract, subscription_contract, _, _ = setup_contracts()

    base_fees = subscription_contract.functions.baseFees(0).call()
    encryptor_fees = subscription_contract.functions.encryptorFees(MAX_NODES, subscription_contract.functions.subscriptionPeriodDuration().call()).call()

    click.echo(f"Approving transfer of {base_fees + encryptor_fees} ERC20 token for subscription contract.")
    tx_hash = erc20_contract.functions.approve(SUBSCRIPTION_CONTRACT_ADDRESS, base_fees + encryptor_fees).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

    click.echo(f"Paying for a new subscription period with {encryptor_slots} encryptor slots.")
    tx_hash = subscription_contract.functions.payForSubscription(encryptor_slots).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.option('--extra-slots', default=1, help='Number of additional encryptor slots to pay for.')
def pay_slots(extra_slots):
    """Pay for additional encryptor slots."""
    _, account = setup_connections()
    _, subscription_contract, _, _ = setup_contracts()

    click.echo(f"Paying for {extra_slots} new encryptor slots.")
    tx_hash = subscription_contract.functions.payForEncryptorSlots(extra_slots).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.option('--num-nodes', default=2, help='Number of nodes to use for the ritual.')
def initiate_ritual(num_nodes):
    """Initiate a ritual."""
    w3, account = setup_connections()
    _, subscription_contract, coordinator_contract, _ = setup_contracts()

    nodes = [u["checksum_address"] for u in requests.get(f"{PORTER_ENDPOINT}/get_ursulas?quantity={num_nodes}").json()["result"]["ursulas"]]
    duration = subscription_contract.functions.subscriptionPeriodDuration().call() + subscription_contract.functions.yellowPeriodDuration().call() + subscription_contract.functions.redPeriodDuration().call()

    click.echo(f"Initiating ritual with {num_nodes} providers for {duration} seconds.")
    tx_hash = coordinator_contract.functions.initiateRitual(subscription_contract.address, nodes, account.address, duration, GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.argument('ritual_id', type=int)
@click.argument('encryptors', nargs=-1)
def add_encryptors(ritual_id, encryptors):
    """Add encryptors to the global allow list for a ritual."""
    _, account = setup_connections()
    _, _, _, global_allow_list_contract = setup_contracts()

    click.echo(f"Adding {len(encryptors)} encryptors to the global allow list for ritual {ritual_id}.")
    tx_hash = global_allow_list_contract.functions.authorize(ritual_id, encryptors).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.argument('ritual_id', type=int)
@click.argument('encryptors', nargs=-1)
def remove_encryptors(ritual_id, encryptors):
    """Remove encryptors from the global allow list for a ritual."""
    _, account = setup_connections()
    _, _, _, global_allow_list_contract = setup_contracts()

    click.echo(f"Removing {len(encryptors)} encryptors from the global allow list for ritual {ritual_id}.")
    tx_hash = global_allow_list_contract.functions.deauthorize(ritual_id, encryptors).transact({'from': account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


if __name__ == "__main__":
    cli()
