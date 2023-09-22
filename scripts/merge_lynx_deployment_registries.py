from scripts.constants import ARTIFACTS_DIR
from scripts.registry import merge_registries

lynx_deployment_registry = ARTIFACTS_DIR / "lynx-alpha-13-registry.json"
lynx_registry_w_subscription_manager = ARTIFACTS_DIR / "contract_registry.json"
output_registry = ARTIFACTS_DIR / "lynx-alpha-13-merged-registry.json"

merge_registries(
    registry_1_filepath=lynx_deployment_registry,
    registry_2_filepath=lynx_registry_w_subscription_manager,
    output_filepath=output_registry,
    deprecated_contracts=["StakeInfo"],
)
