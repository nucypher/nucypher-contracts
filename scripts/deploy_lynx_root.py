#!/usr/bin/python3

from ape import networks, project
from scripts.constants import (
    ARTIFACTS_DIR,
    CONSTRUCTOR_PARAMS_DIR,
    CURRENT_NETWORK,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
)
from scripts.deployment import prepare_deployment
from scripts.registry import registry_from_ape_deployments

VERIFY = CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "lynx-alpha-13-root-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"

OZ_DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]


def main():
    """
    This script deploys only the Lynx TACo Root Application.
    """

    deployer, params = prepare_deployment(
        params_filepath=CONSTRUCTOR_PARAMS_FILEPATH,
        registry_filepath=REGISTRY_FILEPATH,
    )

    reward_token = deployer.deploy(*params.get(project.LynxRitualToken), **params.get_kwargs())

    mock_threshold_staking = deployer.deploy(
        *params.get(project.ThresholdStakingForTACoApplicationMock), **params.get_kwargs()
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
        etherscan = networks.provider.network.explorer
        for deployment in deployments:
            print(f"(i) Verifying {deployment.contract_type.name}...")
            etherscan.publish_contract(deployment.address)
