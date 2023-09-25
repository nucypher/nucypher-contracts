import json

from ape import networks, project

from scripts.constants import ARTIFACTS_DIR

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"

with open(REGISTRY_FILEPATH) as f:
    registry = json.loads(f.read())

deployments = []
for entry in registry:
    contract_type = entry[0]
    contract_container = getattr(project, contract_type)
    contract_instance = contract_container.at(entry[2])
    deployments.append(contract_instance)

etherscan = networks.provider.network.explorer
for deployment in deployments:
    print(f"(i) Verifying {deployment.contract_type.name}...")
    etherscan.publish_contract(deployment.address)
