#!/usr/bin/python3
from ape import project
from ape.cli import get_user_selected_account
from web3 import Web3

PUBLISH = True


def main(account_id=None):
    deployer = get_user_selected_account()

    # Lynx TACo Root Application
    taco_app = project.LynxRootApplication.deploy(
        sender=deployer,
        publish=PUBLISH,
    )

    # Lynx TACo Child Application
    taco_child_app = project.LynxTACoChildApplication.deploy(
        taco_app.address,
        sender=deployer,
        publish=PUBLISH,
    )

    taco_app.setChildApplication(
        taco_child_app.address,
        sender=deployer,
        publish=PUBLISH,
    )

    # Lynx Ritual Token
    ritual_token = project.LynxRitualToken.deploy(
        Web3.to_wei(10_000_000, "ether"), sender=deployer, publish=PUBLISH
    )

    # Lynx Coordinator
    coordinator = project.Coordinator.deploy(
        taco_child_app.address,
        3600,  # 1hr
        4,
        deployer.address,
        ritual_token.address,
        1,  # 1 Wei per second
        sender=deployer,
        publish=PUBLISH,
    )

    taco_child_app.setCoordinator(coordinator.address, sender=deployer)
