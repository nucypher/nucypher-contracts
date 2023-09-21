import json
from pathlib import Path
from typing import List, Optional, Dict

from ape.contracts import ContractInstance
from eth_utils import to_checksum_address


def _get_abi(contract_instance: ContractInstance) -> List[dict]:
    """Returns the ABI of a contract instance."""
    contract_abi = []
    for entry in contract_instance.contract_type.abi:
        contract_abi.append(entry.dict())
    return contract_abi


def _get_name(
    contract_instance: ContractInstance,
    registry_names: Dict[ContractInstance, str]
) -> str:
    """
    Returns the optionally remapped registry name of a contract instance.
    If the contract instance is not remapped, the real contract name is returned.
    """
    real_contract_name = contract_instance.contract_type.name
    contract_name = registry_names.get(
        real_contract_name,  # look up name in registry_names
        real_contract_name   # default to the real contract name
    )
    return contract_name


def _get_entry(
        contract_instance: ContractInstance,
        registry_names: Dict[ContractInstance, str]
) -> List[str]:
    contract_abi = _get_abi(contract_instance)
    contract_name = _get_name(
        contract_instance=contract_instance,
        registry_names=registry_names
    )
    entry = [
        contract_name,
        "v0.0.0",  # TODO: remove version from registry
        to_checksum_address(contract_instance.address),
        contract_abi,
    ]
    return entry


def _write_registry(
        data: List[List[str]],
        filepath: Path
) -> Path:
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
        entry = _get_entry(
            contract_instance=contract_instance,
            registry_names=registry_names
        )
        registry_data.append(entry)

    output_filepath = _write_registry(
        data=registry_data,
        filepath=output_filepath
    )

    return output_filepath
