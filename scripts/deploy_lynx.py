#!/usr/bin/python3
from pathlib import Path

from ape import project
from ape.cli import get_user_selected_account
from scripts.deployment import DeploymentConfig
from scripts.registry import registry_from_ape_deployments
from scripts.utils import check_etherscan_plugin

PUBLISH = False
DEPLOYMENT_CONFIG_FILEPATH = Path(__file__).parent / "configs" / "lynx_config.json"
DEPLOYMENT_REGISTRY_FILEPATH = (
    Path(__file__).parent.parent / "artifacts" / "lynx_testnet_registry.json"
)  # TODO: make unique


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
    """

    check_etherscan_plugin()
    deployer = get_user_selected_account()
    config = DeploymentConfig.from_file(DEPLOYMENT_CONFIG_FILEPATH)

    LynxRootApplication = deployer.deploy(
        *config.get_deployment_params(project.LynxRootApplication, locals()),
        publish=PUBLISH,
    )

    LynxTACoChildApplication = deployer.deploy(
        *config.get_deployment_params(project.LynxTACoChildApplication, locals()),
        publish=PUBLISH,
    )

    LynxRootApplication.setChildApplication(
        LynxTACoChildApplication.address,
        sender=deployer,
        publish=PUBLISH,
    )

    LynxRitualToken = deployer.deploy(
        *config.get_deployment_params(project.LynxRitualToken, locals()),
        publish=PUBLISH,
    )

    # Lynx Coordinator
    Coordinator = deployer.deploy(
        *config.get_deployment_params(project.Coordinator, locals()),
        publish=PUBLISH,
    )

    LynxTACoChildApplication.setCoordinator(Coordinator.address, sender=deployer)

    deployments = [LynxRootApplication, LynxTACoChildApplication, LynxRitualToken, Coordinator]

    registry_from_ape_deployments(
        deployments=deployments, output_filepath=DEPLOYMENT_REGISTRY_FILEPATH
    )
