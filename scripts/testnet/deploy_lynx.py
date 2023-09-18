#!/usr/bin/python3
import os

from ape import project
from ape.cli import get_user_selected_account
from web3 import Web3

PUBLISH = False


def main():
    """
    This script deploys the Lynx TACo Root Application,
    Lynx TACo Child Application, Lynx Ritual Token, and Lynx Coordinator.

    usage: `ape run testnet deploy_lynx --network ethereum:goerli:https://goerli.infura.io/v3/<API_KEY>`

    September 18, 2023, Deployment:
    'LynxRootApplication' deployed to: 0x39F1061d68540F7eb57545C4C731E0945c167016
    'LynxTACoChildApplication' deployed to: 0x892a548592bA66dc3860F75d76cDDb488a838c35
    'Coordinator' deployed to: 0x18566d4590be23e4cb0a8476C80C22096C8c3418
    """

    try:
        import ape_etherscan  # noqa: F401
    except ImportError:
        raise ImportError("Please install the ape-etherscan plugin to use this script.")
    if not os.environ.get("ETHERSCAN_API_KEY"):
        raise ValueError("ETHERSCAN_API_KEY is not set.")

    deployer = get_user_selected_account()

    # Lynx TACo Root Application
    taco_app = deployer.deploy(
        project.LynxRootApplication,
        publish=PUBLISH
    )

    # Lynx TACo Child Application
    taco_child_app = deployer.deploy(
        project.LynxTACoChildApplication,
        taco_app.address,
        publish=PUBLISH,
    )

    taco_app.setChildApplication(
        taco_child_app.address,
        sender=deployer,
        publish=PUBLISH,
    )

    # Lynx Ritual Token
    ritual_token = deployer.deploy(
        project.LynxRitualToken,
        Web3.to_wei(
            10_000_000,
            "ether"
        ),
        publish=PUBLISH
    )

    # Lynx Coordinator
    coordinator = deployer.deploy(
        project.Coordinator,  # coordinator
        taco_child_app.address,  # root_app
        3600,  # timeout (seconds)
        4,  # max_dkg_size
        deployer.address,  # admin
        ritual_token.address,  # currency
        1,  # fee_rate (wei per second)
        publish=PUBLISH,
    )

    taco_child_app.setCoordinator(
        coordinator.address,
        sender=deployer
    )
