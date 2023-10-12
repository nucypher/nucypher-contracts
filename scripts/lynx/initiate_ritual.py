#!/usr/bin/python3


from ape import project
from deployment.constants import ARTIFACTS_DIR, LYNX_NODES
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"
ONE_DAY = 60 * 60 * 24


def main():
    """
    Run this command with ape:
    ape run lynx initiate_ritual --network polygon:mumbai:<polygon-mumbai rpc endpoint>|infura
    """
    check_plugins()
    transactor = Transactor()

    deployments = contracts_from_registry(filepath=REGISTRY_FILEPATH)
    coordinator = deployments[project.Coordinator.contract_type.name]

    global_allow_list = deployments[project.GlobalAllowList.contract_type.name]
    authority = transactor.get_account().address
    providers = list(sorted(LYNX_NODES.keys()))
    duration = ONE_DAY

    while True:
        transactor.transact(
            coordinator.initiateRitual,
            providers,
            authority,
            duration,
            global_allow_list.address
        )
        if not input("Another? [y/n] ").lower().startswith("y"):
            break
