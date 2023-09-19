import json
from pathlib import Path
from typing import List

from ape.contracts import ContractInstance
from eth_utils import to_checksum_address


def registry_from_ape_deployments(
    deployments: List[ContractInstance],
    output_filepath: Path,
):
    """Creates a registry from ape deployments."""
    registry_data = list()

    for contract_instance in deployments:
        abi_json_list = []
        for entry in contract_instance.contract_type.abi:
            abi_json_list.append(entry.dict())

        entry = [
            contract_instance.contract_type.name,
            "v0.0.0",  # TODO: get version from contract
            to_checksum_address(contract_instance.address),
            abi_json_list,
        ]
        registry_data.append(entry)

    with open(output_filepath, "w") as registry_file:
        registry_file.write(json.dumps(registry_data))
