#!/usr/bin/python3

from ape import project
from deployment.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
    CURRENT_NETWORK,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
    OZ_DEPENDENCY,
)
from deployment.registry import registry_from_ape_deployments
from deployment.utils import prepare_deployment, verify_contracts

VERIFY = CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "lynx-alpha-13-root-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"


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

    deployer = prepare_deployment(
        params_filepath=CONSTRUCTOR_PARAMS_FILEPATH,
        registry_filepath=REGISTRY_FILEPATH,
    )

    reward_token = deployer.deploy(project.LynxStakingToken)
    mock_threshold_staking = deployer.deploy(project.TestnetThresholdStaking)
    proxy_admin = deployer.deploy(OZ_DEPENDENCY.ProxyAdmin)
    _ = deployer.deploy(project.TACoApplication)
    proxy = deployer.deploy(OZ_DEPENDENCY.TransparentUpgradeableProxy)

    print("\nWrapping TACoApplication in proxy")
    taco_application = project.TACoApplication.at(proxy.address)

    print(f"\nSetting TACoApplication proxy ({taco_application.address}) on "
          f"ThresholdStakingMock ({mock_threshold_staking.address})")
    mock_threshold_staking.setApplication(taco_application.address, sender=deployer.get_account())

    print("\nInitializing TACoApplication proxy")
    taco_application.initialize(sender=deployer.get_account())

    mock_polygon_root = deployer.deploy(project.MockPolygonRoot)

    print(f"\nSetting child application on TACoApplication proxy "
          f"({taco_application.address}) to MockPolygonChild ({mock_polygon_root.address})")
    taco_application.setChildApplication(mock_polygon_root.address, sender=deployer)

    deployments = [
        reward_token,
        mock_threshold_staking,
        proxy_admin,
        # proxy only (implementation has same contract name so not included)
        taco_application,
        mock_polygon_root,
    ]

    output_filepath = registry_from_ape_deployments(
        deployments=deployments, output_filepath=REGISTRY_FILEPATH
    )
    print(f"(i) Registry written to {output_filepath}!")

    if VERIFY:
        verify_contracts(contracts=deployments)
