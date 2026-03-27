#!/usr/bin/python3

from ape import project

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "upgrades-root.yml"


def main():
    """
    This script upgrades TACoApplication for Lynx on Eth Sepolia.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "lynx.json", chain_id=11155111)

    taco_application_impl = deployer.deploy(project.LynxTACoApplication)

    taco_application_address = instances[project.TACoApplication.contract_type.name].address

    taco_application = deployer.upgradeTo(taco_application_impl, taco_application_address)

    # This line is a workaround to ensure that the contract registry for TACoApplication is updated, not LynxTACoApplication
    taco_application = project.TACoApplication.at(taco_application_address)

    deployments = [
        taco_application,
    ]

    deployer.finalize(deployments=deployments)
