from pathlib import Path

from ape import networks, project
import deployment

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["local"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = networks.network.name
DEPLOYMENT_DIR = Path(deployment.__file__).parent
CONSTRUCTOR_PARAMS_DIR = DEPLOYMENT_DIR / "constructor_params"
ARTIFACTS_DIR = DEPLOYMENT_DIR / "artifacts"
VARIABLE_PREFIX = "$"
PROXY_DECLARATION_DELIMETER = ":"
SPECIAL_VALUE_VARIABLES = {"EMPTY_BYTES": b""}
PROXY_NAME = "TransparentUpgradeableProxy"
OZ_DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]

LYNX_NODES = {
    # staking provider -> operator
    "0xb15d5a4e2be34f4be154a1b08a94ab920ffd8a41": "0x890069745E9497C6f99Db68C4588deC5669F3d3E",
    "0x210eeac07542f815ebb6fd6689637d8ca2689392": "0xf48F720A2Ed237c24F5A7686543D90596bb8D44D",
    "0x48C8039c32F4c6f5cb206A5911C8Ae814929C16B": "0xce057adc39dcD1b3eA28661194E8963481CC48b2",
}
