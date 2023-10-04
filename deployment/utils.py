import json
import os
from pathlib import Path
from typing import List, Dict

import yaml
from ape import networks, project
from ape.contracts import ContractInstance, ContractContainer
from ape_etherscan.utils import API_KEY_ENV_KEY_MAP

from deployment.constants import (
    CURRENT_NETWORK,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS, ARTIFACTS_DIR
)


def _load_yaml(filepath: Path) -> dict:
    """Loads a YAML file."""
    with open(filepath, "r") as file:
        return yaml.safe_load(file)


def _load_json(filepath: Path) -> dict:
    """Loads a JSON file."""
    with open(filepath, "r") as file:
        return json.load(file)


def get_artifact_filepath(config: Dict) -> Path:
    """Returns the filepath of the artifact file."""
    artifact_config = config.get("artifacts", {})
    artifact_dir = Path(artifact_config.get("dir", ARTIFACTS_DIR))
    filename = artifact_config.get("filename")
    if not filename:
        raise ValueError("artifact filename is not set in params file.")
    return artifact_dir / filename


def check_artifact(config: Dict, filepath: Path) -> None:
    """Checks that the deployment has not already been published."""
    deployment = config.get("deployment")
    if not deployment:
        raise ValueError("deployment is not set in params file.")
    chain_id = deployment.get("chain_id")
    if not chain_id:
        raise ValueError("chain_id is not set in params file.")
    if not filepath.exists():
        return
    artifact = _load_json(filepath)
    if chain_id in artifact:
        raise ValueError(f"Deployment is already published for chain_id {chain_id}.")


def check_etherscan_plugin() -> None:
    """
    Checks that the ape-etherscan plugin is installed and that
    the appropriate API key environment variable is set.
    """
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        # unnecessary for local deployment
        return
    try:
        import ape_etherscan  # noqa: F401
    except ImportError:
        raise ImportError("Please install the ape-etherscan plugin to use this script.")
    ecosystem_name = networks.provider.network.ecosystem.name
    explorer_envvar = API_KEY_ENV_KEY_MAP.get(ecosystem_name)
    api_key = os.environ.get(explorer_envvar)
    if not api_key:
        raise ValueError(f"{explorer_envvar} is not set.")


def check_infura_plugin() -> None:
    """Checks that the ape-infura plugin is installed."""
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        return  # unnecessary for local deployment
    try:
        import ape_infura  # noqa: F401
        from ape_infura.provider import _ENVIRONMENT_VARIABLE_NAMES  # noqa: F401
    except ImportError:
        raise ImportError("Please install the ape-infura plugin to use this script.")
    for envvar in _ENVIRONMENT_VARIABLE_NAMES:
        api_key = os.environ.get(envvar)
        if api_key:
            break
    else:
        raise ValueError(
            f"No Infura API key found in "
            f"environment variables: {', '.join(_ENVIRONMENT_VARIABLE_NAMES)}"
        )


def verify_contracts(contracts: List[ContractInstance]) -> None:
    explorer = networks.provider.network.explorer
    for instance in contracts:
        print(f"(i) Verifying {instance.contract_type.name}...")
        explorer.publish_contract(instance.address)


def check_plugins() -> None:
    check_etherscan_plugin()
    check_infura_plugin()


def prepare_deployment(params_filepath: Path) -> Path:
    """Checks that the deployment is ready to be executed."""
    check_plugins()
    config = _load_yaml(params_filepath)
    artifact_filepath = get_artifact_filepath(config)
    check_artifact(config=config, filepath=artifact_filepath)
    return artifact_filepath


def _get_dependency_contract_container(contract: str) -> ContractContainer:
    for dependency_name, dependency_versions in project.dependencies.items():
        if len(dependency_versions) > 1:
            raise ValueError(f"Ambiguous {dependency_name} dependency for {contract}")
        try:
            dependency_api = list(dependency_versions.values())[0]
            contract_container = getattr(dependency_api, contract)
            return contract_container
        except AttributeError:
            continue

    raise ValueError(f"No contract found for {contract}")


def get_contract_container(contract: str) -> ContractContainer:
    try:
        contract_container = getattr(project, contract)
    except AttributeError:
        # not in root project; check dependencies
        contract_container = _get_dependency_contract_container(contract)

    return contract_container
