from pathlib import Path

from ape import networks, config

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["local"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = networks.network.name
DEPLOYMENTS_CONFIG = config.get_config("deployments")["ethereum"][CURRENT_NETWORK][0]
PROJECT_ROOT = Path(__file__).parent.parent
CONSTRUCTOR_PARAMS_DIR = PROJECT_ROOT / "deployments" / "constructor_params"
ARTIFACTS_DIR = PROJECT_ROOT / "deployments" / "artifacts"
ETHERSCAN_API_KEY_ENVVAR = "ETHERSCAN_API_KEY"
