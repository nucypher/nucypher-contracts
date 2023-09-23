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
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx-alpha-13-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx-alpha-13-registry.json"


def main():
    """
    This script deploys the Lynx TACo Root Application,
    Lynx TACo Child Application, Lynx Ritual Token, and Lynx Coordinator.

    September 18, 2023, Goerli Deployment:
    ape run testnet deploy_lynx --network ethereum:goerli:<INFURA_URI>
    'LynxRootApplication' deployed to: 0x39F1061d68540F7eb57545C4C731E0945c167016
    'LynxTACoChildApplication' deployed to: 0x892a548592bA66dc3860F75d76cDDb488a838c35
    'Coordinator' deployed to: 0x18566d4590be23e4cb0a8476C80C22096C8c3418

    September 18, 2023, Mumbai Deployment:
     ape run testnet deploy_lynx --network polygon:mumbai:<INFURA_URI>
    'LynxRootApplication' deployed to: 0xb6400F55857716A3Ff863e6bE867F01F23C71793
    'LynxTACoChildApplication' deployed to: 0x3593f90b19F148FCbe7B00201f854d8839F33F86
    'Coordinator' deployed to: 0x4077ad1CFA834aEd68765dB0Cf3d14701a970a9a

    September 22, 2023, Mumbai Deployment:
    ape-etherscan             0.6.10
    ape-infura                0.6.3
    ape-polygon               0.6.5
    ape-solidity              0.6.9
    eth-ape                   0.6.20

    ape-run deploy_lynx --network polygon:mumbai:infura

    """

    deployer, params = prepare_deployment(
        params_filepath=CONSTRUCTOR_PARAMS_FILEPATH,
        registry_filepath=REGISTRY_FILEPATH,
    )

    root_application = deployer.deploy(
        *params.get(project.LynxRootApplication), **params.get_kwargs()
    )

    child_application = deployer.deploy(
        *params.get(project.LynxTACoChildApplication), **params.get_kwargs()
    )

    print("\nSetting TACo Child application on TACo Root")
    root_application.setChildApplication(
        child_application.address,
        sender=deployer,
    )

    ritual_token = deployer.deploy(*params.get(project.LynxRitualToken), **params.get_kwargs())

    coordinator = deployer.deploy(*params.get(project.Coordinator), **params.get_kwargs())

    print("\nSetting Coordinator on TACo Child application")
    child_application.setCoordinator(coordinator.address, sender=deployer)

    global_allow_list = deployer.deploy(*params.get(project.GlobalAllowList), **params.get_kwargs())

    deployments = [
        root_application,
        child_application,
        ritual_token,
        coordinator,
        global_allow_list,
    ]

    registry_names = {
        root_application.contract_type.name: "TACoApplication",
        child_application.contract_type.name: "TACoChildApplication",
    }

    output_filepath = registry_from_ape_deployments(
        deployments=deployments, registry_names=registry_names, output_filepath=REGISTRY_FILEPATH
    )
    print(f"(i) Registry written to {output_filepath}!")

    if VERIFY:
        etherscan = networks.provider.network.explorer
        for deployment in deployments:
            print(f"(i) Verifying {deployment.contract_type.name}...")
            etherscan.publish_contract(deployment.address)
