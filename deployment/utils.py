import json
import os
from itertools import zip_longest
from pathlib import Path
from typing import Dict, List, Optional

import requests
import yaml
from ape import networks, project
from ape.contracts import ContractContainer, ContractInstance
from ape_etherscan.utils import API_KEY_ENV_KEY_MAP
from eth_utils import to_checksum_address, to_int

from deployment.constants import ARTIFACTS_DIR, MAINNET, PORTER_SAMPLING_ENDPOINTS
from deployment.networks import is_local_network


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


def validate_config(config: Dict) -> Path:
    """
    Checks that the deployment has not already been published for
    the chain_id specified in the params file.
    """
    print("Validating parameters YAML...")

    deployment = config.get("deployment")
    if not deployment:
        raise ValueError("deployment is not set in params file.")

    config_chain_id = deployment.get("chain_id")
    if not config_chain_id:
        raise ValueError("chain_id is not set in params file.")

    contracts = config.get("contracts")
    if not contracts:
        raise ValueError("Constructor parameters file missing 'contracts' field.")

    config_chain_id = int(
        config_chain_id
    )  # Convert chain_id to int here after ensuring it is not None
    chain_mismatch = config_chain_id != networks.provider.network.chain_id
    live_deployment = not is_local_network()
    if chain_mismatch and live_deployment:
        raise ValueError(
            f"chain_id in params file ({config_chain_id}) does not match "
            f"chain_id of current network ({networks.provider.network.chain_id})."
        )

    registry_filepath = get_artifact_filepath(config=config)
    if not registry_filepath.exists():
        return registry_filepath

    registry_chain_ids = map(int, _load_json(registry_filepath).keys())
    if config_chain_id in registry_chain_ids:
        raise ValueError(f"Deployment is already published for chain_id {config_chain_id}.")

    return registry_filepath


def check_etherscan_plugin() -> None:
    """
    Checks that the ape-etherscan plugin is installed and that
    the appropriate API key environment variable is set.
    """
    if is_local_network():
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
    if is_local_network():
        return  # unnecessary for local deployment
    if networks.provider.name != 'infura':
        return  # unnecessary when using a provider different than infura
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
    print("Checking plugins...")
    check_etherscan_plugin()
    check_infura_plugin()


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
    raise ValueError(f"No contract found with name '{contract}'.")


def get_contract_container(contract: str) -> ContractContainer:
    try:
        contract_container = getattr(project, contract)
    except AttributeError:
        # not in root project; check dependencies
        contract_container = _get_dependency_contract_container(contract)

    return contract_container


def registry_filepath_from_domain(domain: str) -> Path:
    p = ARTIFACTS_DIR / f"{domain}.json"
    if not p.exists():
        raise ValueError(f"No registry found for domain '{domain}'")

    return p


def get_chain_name(chain_id: int) -> str:
    """Returns the name of the chain given its chain ID."""
    for ecosystem_name, ecosystem in networks.ecosystems.items():
        for network_name, network in ecosystem.networks.items():
            if network.chain_id == chain_id:
                return f"{ecosystem_name} {network_name}"
    raise ValueError(f"Chain ID {chain_id} not found in networks.")


def sample_nodes(
    domain: str,
    num_nodes: int,
    random_seed: Optional[int] = None,
    duration: Optional[int] = None,
    min_version: Optional[str] = None,
):
    porter_endpoint = PORTER_SAMPLING_ENDPOINTS.get(domain)
    if not porter_endpoint:
        raise ValueError(f"Porter endpoint not found for domain '{domain}'")

    params = {
        "quantity": num_nodes,
    }
    if duration:
        params["duration"] = duration
    if random_seed:
        if domain != MAINNET:
            raise ValueError("'random_seed' is only a valid parameter for mainnet")
        params["random_seed"] = random_seed
    if min_version:
        params["min_version"] = min_version

    response = requests.get(porter_endpoint, params=params)
    response.raise_for_status()

    data = response.json()
    ursulas = data["result"]["ursulas"]
    if domain != MAINNET:
        # /get_ursulas is used for sampling (instead of /bucket_sampling)
        #  so the json returned is slightly different
        ursulas = [u["checksum_address"] for u in ursulas]

    result = sorted(ursulas, key=lambda x: x.lower())
    return result


def _split_into_sorted_pairs(lst) -> List[List[str]]:
    """Splits a list into sorted pairs."""
    if len(lst) % 2 != 0:
        lst.append(lst[-2])  # Use the second-to-last element to fill
    it = iter(lst)
    return [sorted(list(pair)) for pair in zip_longest(it, it)]


def get_heartbeat_cohorts(taco_application) -> List[List[str]]:
    data = taco_application.getActiveStakingProviders(
        0,     # start index
        1000,  # max number of staking providers
        1      # min duration of staking
    )
    staked, staking_providers_info = data
    staking_providers = dict()
    for info in staking_providers_info:
        staking_provider_address = to_checksum_address(info[0:20])
        staking_provider_authorized_tokens = to_int(info[20:32])
        staking_providers[staking_provider_address] = staking_provider_authorized_tokens

    staking_providers_info_pairs = _split_into_sorted_pairs(list(staking_providers))
    return staking_providers_info_pairs

