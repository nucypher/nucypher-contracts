from deployment.constants import ARTIFACTS_DIR
from deployment.registry import contracts_from_registry
from deployment.utils import verify_contracts

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"


def main():
    contracts = contracts_from_registry(REGISTRY_FILEPATH)
    verify_contracts(contracts)
