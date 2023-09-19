#!/usr/bin/python3
import os
from pathlib import Path

import utils
from ape import project
from ape.cli import get_user_selected_account
from utils.registry import registry_from_ape_deployments
from web3 import Web3

PUBLISH = False

# TODO cleanup; uniqueness, existence etc.
DEPLOYMENT_REGISTRY_FILEPATH = (
    Path(utils.__file__).parent / "artifacts" / "lynx_testnet_registry.json"
)


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

    try:
        import ape_etherscan  # noqa: F401
    except ImportError:
        raise ImportError("Please install the ape-etherscan plugin to use this script.")
    if not os.environ.get("ETHERSCAN_API_KEY"):
        raise ValueError("ETHERSCAN_API_KEY is not set.")

    deployer = get_user_selected_account()

    # Lynx TACo Root Application
    LynxRootApplication = deployer.deploy(project.LynxRootApplication, publish=PUBLISH)

    # Lynx TACo Child Application
    LynxTACoChildApplication = deployer.deploy(
        project.LynxTACoChildApplication,
        LynxRootApplication.address,
        publish=PUBLISH,
    )

    LynxRootApplication.setChildApplication(
        LynxTACoChildApplication.address,
        sender=deployer,
        publish=PUBLISH,
    )

    # Lynx Ritual Token
    LynxRitualToken = deployer.deploy(
        project.LynxRitualToken, Web3.to_wei(10_000_000, "ether"), publish=PUBLISH
    )

    # Lynx Coordinator
    Coordinator = deployer.deploy(
        project.Coordinator,  # coordinator
        LynxTACoChildApplication.address,  # root_app
        3600,  # timeout (seconds)
        4,  # max_dkg_size
        deployer.address,  # admin
        LynxRitualToken.address,  # currency
        1,  # fee_rate (wei per second)
        publish=PUBLISH,
    )

    LynxTACoChildApplication.setCoordinator(Coordinator.address, sender=deployer)

    # list deployments
    deployments = [LynxRootApplication, LynxTACoChildApplication, LynxRitualToken, Coordinator]

    registry_from_ape_deployments(
        deployments=deployments, output_filepath=DEPLOYMENT_REGISTRY_FILEPATH
    )
