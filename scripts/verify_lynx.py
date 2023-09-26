from ape import networks
from scripts.constants import ARTIFACTS_DIR
from scripts.deployment import get_contract_container
from scripts.registry import read_registry

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"

registry_entries = read_registry(filepath=REGISTRY_FILEPATH)

deployments = []
for registry_entry in registry_entries:
    contract_type = registry_entry.contract_name
    contract_container = get_contract_container(contract_type)
    contract_instance = contract_container.at(registry_entry.contract_address)
    deployments.append(contract_instance)

etherscan = networks.provider.network.explorer
for deployment in deployments:
    print(f"(i) Verifying {deployment.contract_type.name}...")
    etherscan.publish_contract(deployment.address)
