import os
from pathlib import Path
from urllib.parse import urlencode

import requests
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from deployment.registry import ChainId, RegistryEntry, write_registry
from deployment.utils import _load_json


def get_creation_info(api_key: str, chain_id: int, contract_address: ChecksumAddress) -> tuple:
    networks = {
        1: ("", "etherscan.io"),
        5: ("-goerli", "etherscan.io"),
        80002: ("-testnet", "polygonscan.com"),
    }

    params = {
        "module": "account",
        "action": "txlist",
        "address": contract_address,
        "page": 1,
        "sort": "asc",
        "apikey": api_key,
    }

    network, explorer = networks[chain_id]
    base_url = f"https://api{network}.{explorer}/api"
    url = f"{base_url}?{urlencode(params)}"
    response = requests.get(url)
    data = response.json()

    if data["status"] == "1" and data["result"]:
        # If there are transactions, the first one will be the contract creation transaction
        tx = data["result"][0]
        tx_hash = tx["hash"]
        block_number = tx["blockNumber"]
        deployer = tx["from"]
    else:
        raise ValueError(f"Could not find contract creation transaction for {contract_address}")

    return tx_hash, block_number, to_checksum_address(deployer)


def convert_legacy_registry(
    legacy_filepath: Path,
    output_filepath: Path,
    chain_id: ChainId,
) -> None:
    """Converts a legacy nucypher-style contract registry to a new-style registry."""

    if not legacy_filepath.exists():
        raise FileNotFoundError(f"Legacy registry not found at {legacy_filepath}")
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        raise ValueError("Please set the ETHERSCAN_API_KEY environment variable.")

    legacy_registry_entries = _load_json(filepath=legacy_filepath)
    new_registry_entries = list()
    for entry in legacy_registry_entries:
        name, address, abi = entry[0], entry[2], entry[3]
        tx_hash, block_number, deployer = get_creation_info(
            api_key=api_key, chain_id=chain_id, contract_address=address
        )
        new_registry_entry = RegistryEntry(
            chain_id=chain_id,
            name=name,
            address=address,
            abi=abi,
            tx_hash=tx_hash,
            block_number=block_number,
            deployer=deployer,
        )
        new_registry_entries.append(new_registry_entry)
    write_registry(entries=new_registry_entries, filepath=output_filepath)
    print(f"Converted legacy registry to {output_filepath}")


def convert_legacy_npm_artifacts(directory: Path, chain_id: ChainId, output_filepath: Path) -> None:
    if output_filepath.exists():
        raise FileExistsError(f"Registry already exists at {output_filepath}")

    if not directory.exists():
        raise FileNotFoundError(f"Directory not found at {directory}")

    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        raise ValueError("Please set the ETHERSCAN_API_KEY environment variable.")

    entries = list()
    for filepath in directory.glob("*.json"):
        data = _load_json(filepath=filepath)

        name = filepath.name.replace(".json", "")
        abi = data["abi"]
        address = data["address"]

        tx_hash, block_number, deployer = get_creation_info(
            api_key=api_key, chain_id=chain_id, contract_address=address
        )

        entry = RegistryEntry(
            chain_id=chain_id,
            name=name,
            address=address,
            abi=abi,
            tx_hash=tx_hash,
            block_number=block_number,
            deployer=deployer,
        )

        entries.append(entry)

    write_registry(entries=entries, filepath=output_filepath)
    print(f"Converted legacy registry to {output_filepath}")
