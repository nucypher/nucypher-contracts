import json
import os
import time

import requests
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import geth_poa_middleware

"""
Read from a .env file
"""
load_dotenv()
PROVIDER_URL = os.environ.get("PROVIDER_URL")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

"""Constants"""
BASE_FEE_RATE = 2799999999999360000
MAX_NODES = 10


NUCYPHER_DOMAIN = "lynx"
CHAIN = "80002"
PORTER_ENDPOINT = f"https://porter-{NUCYPHER_DOMAIN}.nucypher.io"
NUM_NODES = 2

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


"""Connect to the testnet"""
w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)
account = w3.eth.account.from_key(PRIVATE_KEY)
nonce = w3.eth.get_transaction_count(account.address)

"""Set up contract instances"""
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

SUBSCRIPTION_PERIOD = subscription_contract.functions.subscriptionPeriodDuration().call()
YELLOW_PERIOD = subscription_contract.functions.yellowPeriodDuration().call()
RED_PERIOD = subscription_contract.functions.redPeriodDuration().call()


base_fees = subscription_contract.functions.baseFees(0).call()
encryptor_fees = subscription_contract.functions.encryptorFees(MAX_NODES, SUBSCRIPTION_PERIOD).call()
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
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
nonce += 1
print(f"Approved ERC20 token for subscription contract. Transaction receipt: {tx_receipt}")

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
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
nonce += 1
print(f"Paid for a new subscription period. Transaction receipt: {tx_receipt}")

"""Pay for additional encryptor slots"""
extra_encryptor_slots = 1
tx = subscription_contract.functions.payForEncryptorSlots(extra_encryptor_slots).build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
    }
)
signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
nonce += 1
print(f"Paid for {encryptor_slots} encryptor slots. Transaction receipt: {tx_receipt}")

"""Initiate a ritual"""
ritual_id = 1
number_of_providers = 7
duration = SUBSCRIPTION_PERIOD + YELLOW_PERIOD + RED_PERIOD
tx = coordinator_contract.functions.processRitualPayment(
    account.address, ritual_id, number_of_providers, duration
).build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
    }
)
signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
nonce += 1
print(
    f"Initiated ritual {ritual_id} with {number_of_providers} providers for {duration} seconds. Transaction receipt: {tx_receipt}"
)


# # Test operations during Yellow period
# end_of_subscription = subscription_contract.functions.getEndOfSubscription().call()
# yellow_period_start = end_of_subscription
# yellow_period_end = yellow_period_start + YELLOW_PERIOD

# # Simulate Yellow period
# w3.geth.miner.stop()
# w3.geth.miner.set_timestamp(yellow_period_start)
# w3.geth.miner.start()

# # Test potential restrictions on adopter operations and decryption during Yellow period
# # ...

# # Test operations during Red period
# red_period_start = yellow_period_end
# red_period_end = red_period_start + RED_PERIOD

# # Simulate Red period
# w3.geth.miner.stop()
# w3.geth.miner.set_timestamp(red_period_start)
# w3.geth.miner.start()

# # Test potential restrictions on adopter operations and decryption during Red period
# # ...

# # Sign a message to test decryption
# data = os.urandom(32)
# digest = Web3.keccak(data)
# signable_message = encode_defunct(digest)
# signed_digest = w3.eth.account.sign_message(signable_message, private_key=ADOPTER_PRIVATE_KEY)
# signature = signed_digest.signature

# # Test decryption during Red period
# is_authorized = global_allow_list_contract.functions.isAuthorized(ritual_id, signature, data).call()
# print(f"Is authorized during Red period: {is_authorized}")
