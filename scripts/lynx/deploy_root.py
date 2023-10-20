#!/usr/bin/python3

from ape import project
from deployment.constants import CONSTRUCTOR_PARAMS_DIR, OZ_DEPENDENCY
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "root.yml"


def main():
    """
    This script deploys only the Proxied Lynx TACo Root Application.

    September 25, 2023, Deployment:
    ape-run deploy_lynx_root --network etherscan:goerli:infura
    ape-etherscan             0.6.10
    ape-infura                0.6.3
    ape-polygon               0.6.5
    ape-solidity              0.6.9
    eth-ape                   0.6.20
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    reward_token = deployer.deploy(project.LynxStakingToken)

    mock_threshold_staking = deployer.deploy(project.TestnetThresholdStaking)

    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin, deployer)

    _ = deployer.deploy(project.TACoApplication)

    proxy = deployer.deploy(OZ_DEPENDENCY.TransparentUpgradeableProxy)
    taco_application = deployer.proxy(project.TACoApplication, proxy)

    deployer.transact(mock_threshold_staking.setApplication, taco_application.address)

    deployer.transact(taco_application.initialize)

    mock_polygon_root = deployer.deploy(project.MockPolygonRoot)
    deployer.transact(taco_application.setChildApplication, mock_polygon_root.address)

    deployments = [
        reward_token,
        mock_threshold_staking,
        proxy_admin,
        # proxy only (implementation has same contract name so not included)
        taco_application,
        mock_polygon_root,
    ]

    deployer.finalize(deployments=deployments)
