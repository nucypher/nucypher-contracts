import json
import os

import requests
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import geth_poa_middleware

"""
Read from a .env file
PROVIDER_URL=https://super-secret-rpc.com/MY-API-KEY
PRIVATE_KEY=0xPleaseDoNotUseThisKeyInProduction0x
"""
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
    w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    account = w3.eth.account.from_key(PRIVATE_KEY)
    nonce = w3.eth.get_transaction_count(account.address)
    return w3, account, nonce


def setup_contracts():
    erc20_contract = w3.eth.contract(address=ERC20_CONTRACT_ADDRESS, abi=ERC20_CONTRACT_ABI)
    subscription_contract = w3.eth.contract(
        address=SUBSCRIPTION_CONTRACT_ADDRESS, abi=SUBSCRIPTION_CONTRACT_ABI
    )
    coordinator_contract = w3.eth.contract(
        address=COORDINATOR_CONTRACT_ADDRESS, abi=COORDINATOR_CONTRACT_ABI
    )
    global_allow_list_contract = w3.eth.contract(
        address=GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS, abi=GLOBAL_ALLOW_LIST_CONTRACT_ABI
    )
    print("ERC20 contract: ", erc20_contract.address)
    print("Subscription contract: ", subscription_contract.address)
    print("Coordinator contract: ", coordinator_contract.address)
    print("Global allow list contract: ", global_allow_list_contract.address)
    return erc20_contract, subscription_contract, coordinator_contract, global_allow_list_contract


def approve_erc20_transfer(erc20_contract, account, nonce, base_fees, encryptor_fees):
    """Approve ERC20 token for subscription contract"""
    tx = erc20_contract.functions.approve(
        SUBSCRIPTION_CONTRACT_ADDRESS, base_fees + encryptor_fees
    ).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
        }
    )
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    _ = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(
        f"Approved transfer of {base_fees + encryptor_fees} ERC20 token for subscription contract."
    )
    print(f"Transaction hash: {tx_hash.hex()}")


def pay_for_subscription_and_slots(subscription_contract, account, nonce, encryptor_slots):
    """Pay for a new subscription period and initial encryptor slots"""
    encryptor_slots = 2
    tx = subscription_contract.functions.payForSubscription(encryptor_slots).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
        }
    )
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    _ = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Paid for a new subscription period with {encryptor_slots} encryptor slots.")
    print(f"Transaction hash: {tx_hash.hex()}")


def pay_for_new_slots(subscription_contract, account, nonce, extra_encryptor_slots):
    """Pay for additional encryptor slots"""
    extra_encryptor_slots = 1
    tx = subscription_contract.functions.payForEncryptorSlots(
        extra_encryptor_slots
    ).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
        }
    )
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    _ = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Paid for {extra_encryptor_slots} new encryptor slots.")
    print(f"Transaction hash: {tx_hash.hex()}")


def initiate_ritual(
    coordinator_contract, account, nonce, subscription_contract, num_nodes
):
    """Initiate a ritual"""
    nodes = [
        u["checksum_address"]
        for u in requests.get(f"{PORTER_ENDPOINT}/get_ursulas?quantity={num_nodes}").json()[
            "result"
        ]["ursulas"]
    ]
    duration = SUBSCRIPTION_PERIOD + YELLOW_PERIOD + RED_PERIOD
    tx = coordinator_contract.functions.initiateRitual(
        subscription_contract.address,
        nodes,
        account.address,
        duration,
        GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
        }
    )
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    _ = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Initiated ritual {ritual_id} with {num_nodes} providers for {duration} seconds.")
    print(f"Transaction hash: {tx_hash.hex()}")


def add_encryptors(global_allow_list_contract, account, nonce, encryptors_addresses, ritual_id):
    tx = global_allow_list_contract.functions.authorize(
        ritual_id,
        encryptors_addresses,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": nonce, # TODO: update nonce consequently
        }
    )

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    _ = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Added {len(encryptors_addresses)} encryptors to the global allow list for ritual {ritual_id}.")
    print(f"Transaction hash: {tx_hash.hex()}")

def remove_encryptors(global_allow_list_contract, account, nonce, encryptors_addresses, ritual_id):
    tx = global_allow_list_contract.functions.deauthorize(
        ritual_id,
        encryptors_addresses,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": nonce, # TODO: update nonce consequently
        }
    )

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Removed encryptors from the global allow list for ritual {ritual_id}.")

if __name__ == "__main__":
    ritual_id = 1
    num_nodes = 2
    encryptor_slots = 2
    extra_encryptor_slots = 1
    w3, account, nonce = setup_connections()
    (
        erc20_contract,
        subscription_contract,
        coordinator_contract,
        global_allow_list_contract,
    ) = setup_contracts()

    SUBSCRIPTION_PERIOD = subscription_contract.functions.subscriptionPeriodDuration().call()
    YELLOW_PERIOD = subscription_contract.functions.yellowPeriodDuration().call()
    RED_PERIOD = subscription_contract.functions.redPeriodDuration().call()

    base_fees = subscription_contract.functions.baseFees(0).call()
    encryptor_fees = subscription_contract.functions.encryptorFees(
        MAX_NODES, SUBSCRIPTION_PERIOD
    ).call()

    approve_erc20_transfer(erc20_contract, account, nonce, base_fees, encryptor_fees)
    input("Press Enter to continue...")
    pay_for_subscription_and_slots(subscription_contract, account, nonce, encryptor_slots)
    input("Press Enter to continue...")
    pay_for_new_slots(subscription_contract, account, nonce, extra_encryptor_slots)
    input("Press Enter to continue...")
    initiate_ritual(
        coordinator_contract, account, nonce, subscription_contract, num_nodes
    )
    input("Press Enter to continue...")

    encryptors = [
        "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
        "0x09f5FF03d0117467b4556FbEC4cC74b475358654",
        "0x47285b814A360f5c39454bc35eEBeA469d1619b3",
        # "0xaa764B4F33097A3d5CA0c9e5FeAFAb8694f02B3E",
        # "0xD155B60Fb856c27416a0B24C5cE01900D4FfbC8E",
    ]
    add_encryptors(global_allow_list_contract, account, nonce, encryptors, ritual_id)
    input("Press Enter to continue...")

    remove_encryptors(global_allow_list_contract, account, nonce, encryptors, ritual_id)
    input("Press Enter to continue...")
