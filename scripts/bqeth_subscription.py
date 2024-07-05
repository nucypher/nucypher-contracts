import json
import os

import requests
from eth_account.messages import encode_defunct
from web3 import Web3

"""Constants"""
BASE_FEE_RATE = 42
MAX_NODES = 10
ENCRYPTORS_FEE_RATE = 77
PACKAGE_DURATION = 10 * 24 * 60 * 60  # 10 days
YELLOW_PERIOD = 24 * 60 * 60  # 1 day
RED_PERIOD = 5 * 24 * 60 * 60  # 5 days

TESTNET_URI = "https://goerli.infura.io/v3/YOUR_PROJECT_ID"
NUCYPHER_DOMAIN = "tapir"
CHAIN = "80002"
PORTER_ENDPOINT = "https://porter-tapir.nucypher.io"
NUM_NODES = 3

with open("deployment/artifacts/tapir.json", "r") as f:
    registry = json.load(f)

# SUBSCRIPTION_CONTRACT_ADDRESS = "0x..."
# SUBSCRIPTION_CONTRACT_ABI = [...]
ERC20_CONTRACT_ADDRESS = registry[CHAIN]["TapirRitualToken"]["address"]
ERC20_CONTRACT_ABI = registry[CHAIN]["TapirRitualToken"]["abi"]
COORDINATOR_CONTRACT_ADDRESS = registry[CHAIN]["Coordinator"]["address"]
COORDINATOR_CONTRACT_ABI = registry[CHAIN]["Coordinator"]["abi"]
GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS = registry[CHAIN]["GlobalAllowList"]["address"]
GLOBAL_ALLOW_LIST_CONTRACT_ABI = registry[CHAIN]["GlobalAllowList"]["abi"]

"""
Replace with your account details
"""
ADOPTER_PRIVATE_KEY = "0x..."
ADOPTER_ADDRESS = "0x..."


"""Connect to the testnet"""
w3 = Web3(Web3.HTTPProvider(TESTNET_URI))

"""Set up contract instances"""
erc20_contract = w3.eth.contract(address=ERC20_CONTRACT_ADDRESS, abi=ERC20_CONTRACT_ABI)
# subscription_contract = w3.eth.contract(address=SUBSCRIPTION_CONTRACT_ADDRESS, abi=SUBSCRIPTION_CONTRACT_ABI)
coordinator_contract = w3.eth.contract(
    address=COORDINATOR_CONTRACT_ADDRESS, abi=COORDINATOR_CONTRACT_ABI
)
global_allow_list_contract = w3.eth.contract(
    address=GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS, abi=GLOBAL_ALLOW_LIST_CONTRACT_ABI
)

"""Approve ERC20 token for subscription contract"""
# erc20_contract.functions.approve(SUBSCRIPTION_CONTRACT_ADDRESS, 10 * BASE_FEE_RATE * PACKAGE_DURATION * MAX_NODES).transact({'from': ADOPTER_ADDRESS})

"""Pay for a new subscription period"""
# tx_hash = subscription_contract.functions.payForSubscription(0).transact({'from': ADOPTER_ADDRESS})
# tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
# print(f"Paid for a new subscription period. Transaction receipt: {tx_receipt}")

"""Pay for encryptor slots"""
encryptor_slots = 5
# tx_hash = subscription_contract.functions.payForEncryptorSlots(encryptor_slots).transact({"from": ADOPTER_ADDRESS})
# tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
# print(f"Paid for {encryptor_slots} encryptor slots. Transaction receipt: {tx_receipt}")

"""Initiate a ritual"""
url = f"{PORTER_ENDPOINT}/get_ursulas?quantity={NUM_NODES}"
response = requests.get(url)
if response.status_code == 200:
    data = response.json()
    print("Porter Response Data:")
    print(data)
    providers = [u["checksum_address"] for u in data["result"]["ursulas"]]
else:
    print(f"Error: {response.status_code} - {response.text}")
# ritual_id = coordinator_contract.functions.initiateRitual(
#     # Replace with the appropriate fee model, providers, authority, duration, and access controller
#     fee_model=SUBSCRIPTION_CONTRACT_ADDRESS,
#     providers=providers,
#     authority=ADOPTER_ADDRESS,
#     duration=PACKAGE_DURATION, # yellow period, red period, _subscriptionPeriodDuration
#     access_controller=GLOBAL_ALLOW_LIST_CONTRACT_ADDRESS
# ).transact({'from': ADOPTER_ADDRESS})
# print(f"Initiated ritual with ID: {ritual_id}")


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
