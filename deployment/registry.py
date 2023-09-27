import json
from enum import Enum
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from ape.contracts import ContractInstance
from deployment.params import get_contract_container
from deployment.utils import check_registry_filepath
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address


class RegistryEntry(NamedTuple):
    """Represents a single entry in a nucypher-style contract registry."""

    contract_name: str
    contract_version: str  # TODO: remove version from registry
    contract_address: ChecksumAddress
    contract_abi: List[Dict]


def _get_abi(contract_instance: ContractInstance) -> List[Dict]:
    """Returns the ABI of a contract instance."""
    contract_abi = []
    for entry in contract_instance.contract_type.abi:
        contract_abi.append(entry.dict())
    return contract_abi


def _get_name(
    contract_instance: ContractInstance, registry_names: Dict[ContractInstance, str]
) -> str:
    """
    Returns the optionally remapped registry name of a contract instance.
    If the contract instance is not remapped, the real contract name is returned.
    """
    real_contract_name = contract_instance.contract_type.name
    contract_name = registry_names.get(
        real_contract_name,  # look up name in registry_names
        real_contract_name,  # default to the real contract name
    )
    return contract_name


def _get_entry(
    contract_instance: ContractInstance, registry_names: Dict[ContractInstance, str]
) -> RegistryEntry:
    contract_abi = _get_abi(contract_instance)
    contract_name = _get_name(contract_instance=contract_instance, registry_names=registry_names)
    entry = RegistryEntry(
        contract_name=contract_name,
        contract_version="v0.0.0",
        contract_address=to_checksum_address(contract_instance.address),
        contract_abi=contract_abi,
    )
    return entry


def read_registry(filepath: Path) -> List[RegistryEntry]:
    with open(filepath, "r") as registry_file:
        json_data = json.load(registry_file)

    registry_entries = list()
    # convert to registry entry
    for json_entry in json_data:
        registry_entry = RegistryEntry(*json_entry)
        registry_entries.append(registry_entry)

    return registry_entries


def write_registry(data: List[RegistryEntry], filepath: Path) -> Path:
    with open(filepath, "w") as registry_file:
        json_data = json.dumps(data, indent=4)
        registry_file.write(json_data)
    return filepath


class ConflictResolution(Enum):
    USE_1 = 1
    USE_2 = 2


def _select_conflict_resolution(
    registry_1_entry, registry_1_filepath, registry_2_entry, registry_2_filepath
) -> ConflictResolution:
    print(f"\n! Conflict detected for {registry_1_entry.contract_name}:")
    print(
        f"[1]: {registry_1_entry.contract_name} at {registry_1_entry.contract_address} "
        f"for {registry_1_filepath}"
    )
    print(
        f"[2]: {registry_2_entry.contract_name} at {registry_2_entry.contract_address} "
        f"for {registry_2_filepath}"
    )
    print("[A]: Abort merge")

    valid_str_answers = [
        str(ConflictResolution.USE_1.value),
        str(ConflictResolution.USE_2.value),
        "A",
    ]
    answer = None
    while answer not in valid_str_answers:
        answer = input(f"Merge resolution, {valid_str_answers}? ")

    if answer == "A":
        print("Merge Aborted!")
        exit(-1)
    return ConflictResolution(int(answer))


def registry_from_ape_deployments(
    deployments: List[ContractInstance],
    output_filepath: Path,
    registry_names: Optional[Dict[str, str]] = None,
) -> Path:
    """Creates a nucypher-style contract registry from ape deployments API."""

    registry_names = registry_names or dict()
    registry_data = list()

    for contract_instance in deployments:
        entry = _get_entry(contract_instance=contract_instance, registry_names=registry_names)
        registry_data.append(entry)

    output_filepath = write_registry(data=registry_data, filepath=output_filepath)
    print(f"(i) Registry written to {output_filepath}!")
    return output_filepath


def merge_registries(
    registry_1_filepath: Path,
    registry_2_filepath: Path,
    output_filepath: Path,
    deprecated_contracts: Optional[List[str]] = None,
) -> Path:
    """Merges two nucypher-style contract registries created from ape deployments API."""
    check_registry_filepath(registry_filepath=output_filepath)

    registry_1_entries = read_registry(registry_1_filepath)
    registry_2_entries = read_registry(registry_2_filepath)

    deprecated_contracts = [] if deprecated_contracts is None else deprecated_contracts

    # obtain dictionary of contract name -> registry entry
    # exclude any deprecated contracts
    registry_1_contracts_dict = {
        entry.contract_name: entry
        for entry in registry_1_entries
        if entry.contract_name not in deprecated_contracts
    }
    registry_2_contracts_dict = {
        entry.contract_name: entry
        for entry in registry_2_entries
        if entry.contract_name not in deprecated_contracts
    }

    merged_entries = []

    # registry 1 entries
    registry_1_contract_names = list(registry_1_contracts_dict.keys())
    for contract_name in registry_1_contract_names:
        registry_1_entry = registry_1_contracts_dict[contract_name]
        if contract_name in registry_2_contracts_dict:
            # conflict found
            registry_2_entry = registry_2_contracts_dict[contract_name]
            result = _select_conflict_resolution(
                registry_1_entry, registry_1_filepath, registry_2_entry, registry_2_filepath
            )
            if result == ConflictResolution.USE_1:
                merged_entries.append(registry_1_entry)
            else:
                # USE_2
                merged_entries.append(registry_2_entry)

            # ensure registry_2 entry not repeated
            # either usurped by registry_entry_1 OR already added to combined list
            del registry_2_contracts_dict[contract_name]
            continue

        merged_entries.append(registry_1_entry)

    # registry 2 entries
    merged_entries.extend(registry_2_contracts_dict.values())

    write_registry(data=merged_entries, filepath=output_filepath)
    print(f"Merged registry output to {output_filepath}")

    return output_filepath


def contracts_from_registry(filepath: Path) -> Dict[str, ContractInstance]:
    registry_entries = read_registry(filepath=filepath)
    deployments = dict()
    for registry_entry in registry_entries:
        contract_type = registry_entry.contract_name
        contract_container = get_contract_container(contract_type)
        contract_instance = contract_container.at(registry_entry.contract_address)
        deployments[contract_type] = contract_instance
    return deployments
