import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from ape.contracts import ContractInstance
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from scripts.utils import check_registry_filepath


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


def _read_registry(filepath: Path) -> List[RegistryEntry]:
    with open(filepath, "r") as registry_file:
        json_data = json.load(registry_file)

    registry_entries = list()
    # convert to registry entry
    for json_entry in json_data:
        registry_entry = RegistryEntry(*json_entry)
        registry_entries.append(registry_entry)

    return registry_entries


def _write_registry(data: List[RegistryEntry], filepath: Path) -> Path:
    with open(filepath, "w") as registry_file:
        json_data = json.dumps(data)
        registry_file.write(json_data)
    return filepath


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

    output_filepath = _write_registry(data=registry_data, filepath=output_filepath)

    return output_filepath


def merge_registries(
    registry_1_filepath: Path,
    registry_2_filepath: Path,
    output_filepath: Path,
) -> Path:
    """Merges two nucypher-style contract registries created from ape deployments API."""
    check_registry_filepath(registry_filepath=output_filepath)

    registry_1_entries = _read_registry(registry_1_filepath)
    registry_2_entries = _read_registry(registry_2_filepath)

    # handle case of conflicting contract names
    registry_1_contract_names = {entry.contract_name for entry in registry_1_entries}
    registry_2_contract_names = {entry.contract_name for entry in registry_2_entries}

    common_contracts = registry_1_contract_names.intersection(registry_2_contract_names)
    if len(common_contracts) > 0:
        print(f"Provided registries have conflicting contracts: {common_contracts}")
        print("Aborting merge!")
        exit(-1)

    combined_entries = [*registry_1_entries, *registry_2_entries]
    _write_registry(data=combined_entries, filepath=output_filepath)

    return output_filepath
