from pathlib import Path

from ape import networks, project

import deployment

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["local"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = networks.network.name
DEPLOYMENT_DIR = Path(deployment.__file__).parent
CONSTRUCTOR_PARAMS_DIR = DEPLOYMENT_DIR / "constructor_params"
ARTIFACTS_DIR = DEPLOYMENT_DIR / "artifacts"
ETHERSCAN_API_KEY_ENVVAR = "ETHERSCAN_API_KEY"
WEB3_INFURA_API_KEY_ENVVAR = "WEB3_INFURA_API_KEY"
NULL_ADDRESS = "0x" + "0" * 40
VARIABLE_PREFIX = "$"
PROXY_DECLARATION_DELIMETER = ":"
SPECIAL_VALUE_VARIABLES = {"EMPTY_BYTES": b""}
PROXY_NAME = "TransparentUpgradeableProxy"
OZ_DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]
