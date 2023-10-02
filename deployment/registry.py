import json
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Union

from ape.contracts import ContractInstance
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from web3.types import ABI

from deployment.params import get_contract_container
from deployment.utils import check_registry_filepath


ChainId = int
ContractName = str
ContractArtifacts = Dict[ContractName, Union[ChecksumAddress, ABI]]
RegistryData = Dict[ChainId, ContractArtifacts]


class ContractEntry(NamedTuple):
    """Represents a single entry in a nucypher-style contract registry."""
    chain_id: ChainId
    name: ContractName
    address: ChecksumAddress
    abi: ABI


def _get_abi(contract_instance: ContractInstance) -> ABI:
    """Returns the ABI of a contract instance."""
    contract_abi = list()
    for entry in contract_instance.contract_type.abi:
        contract_abi.append(entry.dict())
    return contract_abi


def _get_name(
    contract_instance: ContractInstance, registry_names: Dict[ContractInstance, ContractName]
) -> ContractName:
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
    contract_instance: ContractInstance, registry_names: Dict[ContractInstance, ContractName]
) -> ContractEntry:
    contract_abi = _get_abi(contract_instance)
    contract_name = _get_name(contract_instance=contract_instance, registry_names=registry_names)
    chain_id = contract_instance.chain_manager.chain_id
    entry = ContractEntry(
        chain_id=chain_id,
        name=contract_name,
        address=to_checksum_address(contract_instance.address),
        abi=contract_abi
    )
    return entry


def read_registry(filepath: Path) -> List[ContractEntry]:
    with open(filepath, "r") as file:
        data = json.load(file)
    registry_entries = list()
    for chain_id, entries in data.items():
        for contract_name, artifacts in entries.items():
            registry_entry = ContractEntry(
                chain_id=int(chain_id),
                name=contract_name,
                address=artifacts["address"],
                abi=artifacts["abi"]
            )
            registry_entries.append(registry_entry)
    return registry_entries


def write_registry(data: RegistryData, filepath: Path) -> Path:
    with open(filepath, "w") as file:
        data = json.dumps(data, indent=4)
        file.write(data)
    return filepath


class ConflictResolution(Enum):
    USE_1 = 1
    USE_2 = 2


def _select_conflict_resolution(
    registry_1_entry, registry_1_filepath, registry_2_entry, registry_2_filepath
) -> ConflictResolution:
    print(f"\n! Conflict detected for {registry_1_entry.name}:")
    print(
        f"[1]: {registry_1_entry.name} at {registry_1_entry.address} "
        f"for {registry_1_filepath}"
    )
    print(
        f"[2]: {registry_2_entry.name} at {registry_2_entry.address} "
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
    registry_names: Optional[Dict[ContractName, ContractName]] = None,
) -> Path:
    """Creates a nucypher-style contract registry from ape deployments API."""

    registry_names = registry_names or dict()
    registry_data = defaultdict(dict)

    for contract_instance in deployments:
        entry = _get_entry(contract_instance=contract_instance, registry_names=registry_names)
        registry_data[entry.chain_id][entry.name] = {
            "address": entry.address,
            "abi": entry.abi
        }

    output_filepath = write_registry(data=registry_data, filepath=output_filepath)
    print(f"(i) Registry written to {output_filepath}!")
    return output_filepath


def merge_registries(
        registry_1_filepath: Path,
        registry_2_filepath: Path,
        output_filepath: Path,
        deprecated_contracts: Optional[List[ContractName]] = None,
) -> Path:
    """Merges two nucypher-style contract registries into a single registry."""

    # Ensure the output file path is valid
    check_registry_filepath(registry_filepath=output_filepath)

    # If no deprecated contracts are specified, use an empty list
    deprecated_contracts = deprecated_contracts or []

    # Read the registries, excluding deprecated contracts
    reg1 = {e.name: e for e in read_registry(registry_1_filepath) if e.name not in deprecated_contracts}
    reg2 = {e.name: e for e in read_registry(registry_2_filepath) if e.name not in deprecated_contracts}

    merged = defaultdict(dict)

    # Iterate over all unique contract names across both registries
    for name in set(reg1) | set(reg2):
        entry = reg1.get(name) or reg2.get(name)
        conflict_entry = reg2.get(name) if name in reg1 else None
        conflict = conflict_entry and (entry.chain_id == conflict_entry.chain_id)
        if conflict:
            resolution = _select_conflict_resolution(
                registry_1_entry=entry,
                registry_2_entry=conflict_entry,
                registry_1_filepath=registry_1_filepath,
                registry_2_filepath=registry_2_filepath
            )

            # Choose the entry based on the resolution strategy
            selected_entry = entry if resolution == ConflictResolution.USE_1 else conflict_entry
        else:
            selected_entry = entry

        # Merge the selected entry into the merged registry
        merged[selected_entry.chain_id][name] = {
            "address": selected_entry.address,
            "abi": selected_entry.abi
        }

    # Write the merged registry to the specified output file path
    write_registry(data=merged, filepath=output_filepath)
    print(f"Merged registry output to {output_filepath}")
    return output_filepath


def contracts_from_registry(filepath: Path) -> Dict[str, ContractInstance]:
    """Returns a dictionary of contract instances from a nucypher-style contract registry."""
    registry_entries = read_registry(filepath=filepath)
    deployments = dict()
    for registry_entry in registry_entries:
        contract_type = registry_entry.name
        contract_container = get_contract_container(contract_type)
        contract_instance = contract_container.at(registry_entry.address)
        deployments[contract_type] = contract_instance
    return deployments
