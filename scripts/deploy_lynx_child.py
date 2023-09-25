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
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "lynx-alpha-13-child-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"

OZ_DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]


def main():
    """
    This script deploys the Mock Lynx TACo Root Application,
    Proxied Lynx TACo Child Application, Lynx Ritual Token, and Lynx Coordinator.

    September 25, 2023, Deployment:
    ape-run deploy_lynx --network polygon:mumbai:infura
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

    root_application = deployer.deploy(
        *params.get(project.LynxMockTACoApplication), **params.get_kwargs()
    )

    proxy_admin = deployer.deploy(*params.get(OZ_DEPENDENCY.ProxyAdmin), **params.get_kwargs())

    taco_implementation = deployer.deploy(*params.get(project.LynxTACoChildApplication), **params.get_kwargs())

    proxy = deployer.deploy(
        *params.get(OZ_DEPENDENCY.TransparentUpgradeableProxy), **params.get_kwargs()
    )

    print("\nWrapping TACoChildApplication in proxy")
    taco_child_application = project.LynxTACoChildApplication.at(proxy.address)

    print("\nSetting TACo Child application on TACo Root")
    root_application.setChildApplication(
        taco_child_application.address,
        sender=deployer,
    )

    ritual_token = deployer.deploy(*params.get(project.LynxRitualToken), **params.get_kwargs())

    coordinator = deployer.deploy(*params.get(project.Coordinator), **params.get_kwargs())

    print(f"\nInitialize TACoChildApplication proxy with Coordinator {coordinator.address}")
    taco_child_application.initialize(coordinator.address, sender=deployer)

    global_allow_list = deployer.deploy(*params.get(project.GlobalAllowList), **params.get_kwargs())

    deployments = [
        root_application,
        proxy_admin,
        taco_implementation,
        taco_child_application,
        ritual_token,
        coordinator,
        global_allow_list,
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
