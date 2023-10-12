#!/usr/bin/python3


from ape import project
from eth_utils import to_checksum_address

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Transactor
from deployment.registry import contracts_from_registry
from deployment.utils import check_plugins

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx.json"


def main():
    check_plugins()
    transactor = Transactor()
    deployments = contracts_from_registry(filepath=REGISTRY_FILEPATH)
    global_allow_list = deployments[project.GlobalAllowList.contract_type.name]
    ritual_id = int(input("Enter ritual ID: "))
    addresses = [to_checksum_address(input("Enter address to authorize: "))]
    transactor.transact(global_allow_list.authorize, ritual_id, addresses)
