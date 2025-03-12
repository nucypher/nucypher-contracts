#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR,
)
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "tapir" / "infraction.yml"
TAPIR_REGISTRY = ARTIFACTS_DIR / "tapir.json"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)
    infraction = deployer.deploy(project.InfractionCollector)
    deployments = [infraction]
    deployer.finalize(deployments=deployments)

