"""
# Prerequisites
`pip install web3 requests python-dotenv click`

# Setup
Create a .env file in the project root directory and add the following environment variables:
```
PROVIDER_URL=<your_provider_url>
PRIVATE_KEY=<your_private_key>
```

# Usage
To use the BqETH Subscription CLI, run the bqeth_subscription.py script with the desired command and options. Here are the available commands:

- pay-subscription: Pay for a new subscription period and initial encryptor slots.
  - --encryptor-slots: Number of encryptor slots to pay for (default: 2).

- pay-slots: Pay for additional encryptor slots.
  ---extra-slots: Number of additional encryptor slots to pay for (default: 1).

- initiate-ritual: Initiate a ritual.
  - --num-nodes: Number of nodes to use for the ritual (default: 2).

- add-encryptors: Add encryptors to the global allow list for a ritual.
  - ritual_id: ID of the ritual.
  - encryptors: List of encryptor addresses to add.

- remove-encryptors: Remove encryptors from the global allow list for a ritual.
  - ritual_id: ID of the ritual.
  - encryptors: List of encryptor addresses to remove.

Example usage:
```
python bqeth_subscription.py pay-subscription --encryptor-slots 3
python bqeth_subscription.py pay-slots --extra-slots 2
python bqeth_subscription.py initiate-ritual --num-nodes 4
python bqeth_subscription.py add-encryptors 1 0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600 0x09f5FF03d0117467b4556FbEC4cC74b475358654
python bqeth_subscription.py remove-encryptors 1 0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600 0x09f5FF03d0117467b4556FbEC4cC74b475358654
```
"""
import json
import os
import click
import functools
from collections import namedtuple

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

# Define a namedtuple to hold the required objects
Context = namedtuple('Context', ['w3', 'account', 'erc20_contract', 'subscription_contract', 'coordinator_contract', 'global_allow_list_contract'])

def setup_connections():
    """Set up Web3 connections."""
    w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    account = w3.eth.account.from_key(PRIVATE_KEY)
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    return w3, account

def setup_contracts(w3):
    """Set up contract instances."""
    erc20_contract = w3.eth.contract(address=ERC20_CONTRACT_ADDRESS, abi=ERC20_CONTRACT_ABI)
    subscription_contract = w3.eth.contract(address=SUBSCRIPTION_CONTRACT_ADDRESS, abi=SUBSCRIPTION_CONTRACT_ABI)
    coordinator_contract = w3.eth.contract(address=COORDINATOR_CONTRACT_ADDRESS, abi=COORDINATOR_CONTRACT_ABI)
    global_allow_list_contract = w3.eth.contract(address=GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS, abi=GLOBAL_ALLOW_LIST_CONTRACT_ABI)
    click.echo(f"ERC20 contract: {erc20_contract.address}")
    click.echo(f"Subscription contract: {subscription_contract.address}")
    click.echo(f"Coordinator contract: {coordinator_contract.address}")
    click.echo(f"Global allow list contract: {global_allow_list_contract.address}")
    return erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract

def setup_context(func):
    """Decorator to set up connections and contracts before executing the command function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        w3, account = setup_connections()
        erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract = setup_contracts(w3)
        context = Context(w3, account, erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract)
        return func(context, *args, **kwargs)
    return wrapper

@click.group()
def cli():
    """BqETH Subscription CLI"""
    pass

@cli.command()
@click.option('--encryptor-slots', default=2, help='Number of encryptor slots to pay for.')
@setup_context
def pay_subscription(context, encryptor_slots):
    """Pay for a new subscription period and initial encryptor slots."""
    base_fees = context.subscription_contract.functions.baseFees(0).call()
    encryptor_fees = context.subscription_contract.functions.encryptorFees(MAX_NODES, context.subscription_contract.functions.subscriptionPeriodDuration().call()).call()

    click.echo(f"Approving transfer of {base_fees + encryptor_fees} ERC20 token for subscription contract.")
    tx_hash = context.erc20_contract.functions.approve(SUBSCRIPTION_CONTRACT_ADDRESS, base_fees + encryptor_fees).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

    click.echo(f"Paying for a new subscription period with {encryptor_slots} encryptor slots.")
    tx_hash = context.subscription_contract.functions.payForSubscription(encryptor_slots).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

@cli.command()
@click.option('--extra-slots', default=1, help='Number of additional encryptor slots to pay for.')
@setup_context
def pay_slots(context, extra_slots):
    """Pay for additional encryptor slots."""
    click.echo(f"Paying for {extra_slots} new encryptor slots.")
    tx_hash = context.subscription_contract.functions.payForEncryptorSlots(extra_slots).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

@cli.command()
@click.option('--num-nodes', default=2, help='Number of nodes to use for the ritual.')
@setup_context
def initiate_ritual(context, num_nodes):
    """Initiate a ritual."""
    nodes = [u["checksum_address"] for u in requests.get(f"{PORTER_ENDPOINT}/get_ursulas?quantity={num_nodes}").json()["result"]["ursulas"]]
    duration = context.subscription_contract.functions.subscriptionPeriodDuration().call() + context.subscription_contract.functions.yellowPeriodDuration().call() + context.subscription_contract.functions.redPeriodDuration().call()

    click.echo(f"Initiating ritual with {num_nodes} providers for {duration} seconds.")
    tx_hash = context.coordinator_contract.functions.initiateRitual(context.subscription_contract.address, nodes, context.account.address, duration, GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

@cli.command()
@click.argument('ritual_id', type=int)
@click.argument('encryptors', nargs=-1)
@setup_context
def add_encryptors(context, ritual_id, encryptors):
    """Add encryptors to the global allow list for a ritual."""
    click.echo(f"Adding {len(encryptors)} encryptors to the global allow list for ritual {ritual_id}.")
    tx_hash = context.global_allow_list_contract.functions.authorize(ritual_id, encryptors).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

@cli.command()
@click.argument('ritual_id', type=int)
@click.argument('encryptors', nargs=-1)
@setup_context
def remove_encryptors(context, ritual_id, encryptors):
    """Remove encryptors from the global allow list for a ritual."""
    click.echo(f"Removing {len(encryptors)} encryptors from the global allow list for ritual {ritual_id}.")
    tx_hash = context.global_allow_list_contract.functions.deauthorize(ritual_id, encryptors).transact({'from': context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

if __name__ == "__main__":
    cli()
