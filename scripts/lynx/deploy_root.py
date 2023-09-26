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

    deployer, params = prepare_deployment(
        params_filepath=CONSTRUCTOR_PARAMS_FILEPATH,
        registry_filepath=REGISTRY_FILEPATH,
    )

    reward_token = deployer.deploy(*params.get(project.LynxStakingToken), **params.get_kwargs())

    mock_threshold_staking = deployer.deploy(
        *params.get(project.TestnetThresholdStaking), **params.get_kwargs()
    )

    proxy_admin = deployer.deploy(*params.get(OZ_DEPENDENCY.ProxyAdmin), **params.get_kwargs())

    _ = deployer.deploy(*params.get(project.TACoApplication), **params.get_kwargs())

    proxy = deployer.deploy(
        *params.get(OZ_DEPENDENCY.TransparentUpgradeableProxy), **params.get_kwargs()
    )

    print("\nWrapping TACoApplication in proxy")
    taco_application = project.TACoApplication.at(proxy.address)

    print("\nSetting TACoApplication on ThresholdStakingMock")
    mock_threshold_staking.setApplication(taco_application.address, sender=deployer)

    print("\nInitialize TACoApplication proxy")
    taco_application.initialize(sender=deployer)

    mock_taco_child = deployer.deploy(
        *params.get(project.LynxMockTACoChildApplication), **params.get_kwargs()
    )

    print(f"\nSetting child application {mock_taco_child.address} on TACoApplication")
    taco_application.setChildApplication(mock_taco_child.address, sender=deployer)

    deployments = [
        reward_token,
        proxy_admin,
        mock_threshold_staking,
        proxy,
        taco_application,
        mock_taco_child,
    ]

    output_filepath = registry_from_ape_deployments(
        deployments=deployments, output_filepath=REGISTRY_FILEPATH
    )
    print(f"(i) Registry written to {output_filepath}!")

    if VERIFY:
        verify_contracts(contracts=deployments)