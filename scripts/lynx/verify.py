from ape import networks
from deployment.constants import ARTIFACTS_DIR
from deployment.registry import contracts_from_registry
from deployment.utils import verify_contracts

LYNX_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"


def main():
    contracts = contracts_from_registry(
        filepath=LYNX_REGISTRY_FILEPATH, chain_id=networks.active_provider.chain_id
    )
    verify_contracts(list(contracts.values()))
