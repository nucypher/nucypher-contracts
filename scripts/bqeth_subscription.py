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
python bqeth_subscription.py --domain lynx pay-subscription --encryptor-slots 3
python bqeth_subscription.py --domain lynx pay-slots --extra-slots 2
python bqeth_subscription.py --domain lynx initiate-ritual --num-nodes 4
python bqeth_subscription.py --domain lynx add-encryptors 1 0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600 0x09f5FF03d0117467b4556FbEC4cC74b475358654
python bqeth_subscription.py --domain lynx remove-encryptors 1 0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600 0x09f5FF03d0117467b4556FbEC4cC74b475358654
```
"""

import functools
import json
import os
from typing import NamedTuple

import click
import requests
from dotenv import load_dotenv
from web3 import Web3
from web3.contract import Contract
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware
from eth_account.signers.local import LocalAccount


def build_constants(domain, provider_url, private_key):
    DOMAIN_TO_CHAIN = {"lynx": "80002", "tapir": "80002", "mainnet": "137"}
    chain = DOMAIN_TO_CHAIN[domain]
    PORTER_ENDPOINT = f"https://porter-{domain}.nucypher.community"

    with open(f"deployment/artifacts/{domain}.json", "r") as f:
        registry = json.load(f)

    return {
        "PROVIDER_URL": provider_url,
        "PRIVATE_KEY": private_key,
        "PORTER_ENDPOINT": PORTER_ENDPOINT,
        "SUBSCRIPTION_CONTRACT_ADDRESS": registry[chain]["BqETHSubscription"]["address"],
        "SUBSCRIPTION_CONTRACT_ABI": registry[chain]["BqETHSubscription"]["abi"],
        "ERC20_CONTRACT_ADDRESS": registry[chain][f"{domain.title()}RitualToken"]["address"],
        "ERC20_CONTRACT_ABI": registry[chain][f"{domain.title()}RitualToken"]["abi"],
        "COORDINATOR_CONTRACT_ADDRESS": registry[chain]["Coordinator"]["address"],
        "COORDINATOR_CONTRACT_ABI": registry[chain]["Coordinator"]["abi"],
        "GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS": registry[chain]["GlobalAllowList"]["address"],
        "GLOBAL_ALLOW_LIST_CONTRACT_ABI": registry[chain]["GlobalAllowList"]["abi"],
    }


class Context(NamedTuple):
    w3: Web3
    account: LocalAccount
    erc20_contract: Contract
    subscription_contract: Contract
    coordinator_contract: Contract
    global_allow_list_contract: Contract
    constants: dict


def setup_connections(constants):
    """Set up Web3 connections."""
    w3 = Web3(Web3.HTTPProvider(constants["PROVIDER_URL"]))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    account = w3.eth.account.from_key(constants["PRIVATE_KEY"])
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    return w3, account


def setup_contracts(w3, constants):
    """Set up contract instances."""
    erc20_contract = w3.eth.contract(
        address=constants["ERC20_CONTRACT_ADDRESS"], abi=constants["ERC20_CONTRACT_ABI"]
    )
    subscription_contract = w3.eth.contract(
        address=constants["SUBSCRIPTION_CONTRACT_ADDRESS"],
        abi=constants["SUBSCRIPTION_CONTRACT_ABI"],
    )
    coordinator_contract = w3.eth.contract(
        address=constants["COORDINATOR_CONTRACT_ADDRESS"], abi=constants["COORDINATOR_CONTRACT_ABI"]
    )
    global_allow_list_contract = w3.eth.contract(
        address=constants["GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS"],
        abi=constants["GLOBAL_ALLOW_LIST_CONTRACT_ABI"],
    )
    click.echo(f"ERC20 contract: {erc20_contract.address}")
    click.echo(f"Subscription contract: {subscription_contract.address}")
    click.echo(f"Coordinator contract: {coordinator_contract.address}")
    click.echo(f"Global allow list contract: {global_allow_list_contract.address}")
    return erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract


def setup_context(func):
    """Decorator to set up connections and contracts before executing the command function."""

    @functools.wraps(func)
    @click.pass_context
    def wrapper(ctx, *args, **kwargs):
        constants = ctx.obj["constants"]
        w3, account = setup_connections(constants)
        (
            erc20_contract,
            subscription_contract,
            coordinator_contract,
            global_allow_list_contract,
        ) = setup_contracts(w3, constants)
        context = Context(
            w3,
            account,
            erc20_contract,
            subscription_contract,
            coordinator_contract,
            global_allow_list_contract,
            constants,
        )
        return func(context, *args, **kwargs)

    return wrapper


@click.group()
@click.option("--domain", default="lynx", help="NuCypher domain.")
@click.pass_context
def cli(ctx, domain):
    """BqETH Subscription CLI"""
    load_dotenv(override=True)
    provider_url = os.environ.get("PROVIDER_URL")
    private_key = os.environ.get("PRIVATE_KEY")
    ctx.ensure_object(dict)
    ctx.obj["constants"] = build_constants(domain, provider_url, private_key)


@cli.command()
@click.option("--encryptor-slots", default=2, help="Number of encryptor slots to pay for.")
@setup_context
def pay_subscription(context, encryptor_slots):
    """Pay for a new subscription period and initial encryptor slots."""
    base_fees = context.subscription_contract.functions.baseFees(0).call()
    encryptor_fees = context.subscription_contract.functions.encryptorFees(
        encryptor_slots, context.subscription_contract.functions.subscriptionPeriodDuration().call()
    ).call()

    click.echo(
        f"Approving transfer of {base_fees + encryptor_fees} ERC20 token for subscription contract."
    )
    tx_hash = context.erc20_contract.functions.approve(
        context.constants["SUBSCRIPTION_CONTRACT_ADDRESS"], base_fees + encryptor_fees
    ).transact({"from": context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")

    click.echo(f"Paying for a new subscription period with {encryptor_slots} encryptor slots.")
    tx_hash = context.subscription_contract.functions.payForSubscription(encryptor_slots).transact(
        {"from": context.account.address}
    )
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.option("--extra-slots", default=1, help="Number of additional encryptor slots to pay for.")
@setup_context
def pay_slots(context, extra_slots):
    """Pay for additional encryptor slots."""
    click.echo(f"Paying for {extra_slots} new encryptor slots.")
    tx_hash = context.subscription_contract.functions.payForEncryptorSlots(extra_slots).transact(
        {"from": context.account.address}
    )
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.option("--num-nodes", default=2, help="Number of nodes to use for the ritual.")
@setup_context
def initiate_ritual(context, num_nodes):
    """Initiate a ritual."""
    nodes = list(sorted(
        [
            u["checksum_address"]
            for u in requests.get(
                f"{context.constants['PORTER_ENDPOINT']}/get_ursulas?quantity={num_nodes}"
            ).json()["result"]["ursulas"]
        ]
    ))
    start_of_subscription = context.subscription_contract.functions.startOfSubscription().call()
    duration = (
        context.subscription_contract.functions.subscriptionPeriodDuration().call()
        + context.subscription_contract.functions.yellowPeriodDuration().call()
        + context.subscription_contract.functions.redPeriodDuration().call()
    )
    if start_of_subscription > 0:
        click.echo(
            "Subscription has already started. Subtracting the elapsed time from the duration."
        )
        now = context.w3.eth.get_block("latest")["timestamp"]
        elapsed = now - start_of_subscription + 100
        duration -= elapsed
    click.echo(f"Initiating ritual with {num_nodes} providers for {duration} seconds.")
    tx_hash = context.coordinator_contract.functions.initiateRitual(
        context.subscription_contract.address,
        nodes,
        context.account.address,
        duration,
        context.constants["GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS"],
    ).transact({"from": context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.argument("ritual_id", type=int)
@click.argument("encryptors", nargs=-1)
@setup_context
def add_encryptors(context, ritual_id, encryptors):
    """Add encryptors to the global allow list for a ritual."""
    click.echo(
        f"Adding {len(encryptors)} encryptors to the global allow list for ritual {ritual_id}."
    )
    tx_hash = context.global_allow_list_contract.functions.authorize(
        ritual_id, encryptors
    ).transact({"from": context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


@cli.command()
@click.argument("ritual_id", type=int)
@click.argument("encryptors", nargs=-1)
@setup_context
def remove_encryptors(context, ritual_id, encryptors):
    """Remove encryptors from the global allow list for a ritual."""
    click.echo(
        f"Removing {len(encryptors)} encryptors from the global allow list for ritual {ritual_id}."
    )
    tx_hash = context.global_allow_list_contract.functions.deauthorize(
        ritual_id, encryptors
    ).transact({"from": context.account.address})
    click.echo(f"Transaction hash: {tx_hash.hex()}")


if __name__ == "__main__":
    cli()
