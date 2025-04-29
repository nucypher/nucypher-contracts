#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "signing-infra.yml"


def main():
    """
    This script deploys the Signing Infrastructure on Lynx/Amoy.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    _ = deployer.deploy(project.ThresholdSigningMultisig)
    threshold_signing_multisig_clone_factory = deployer.deploy(
        project.ThresholdSigningMultisigCloneFactory
    )
    signing_coordinator = deployer.deploy(project.SigningCoordinator)
    deployer.transact(
        signing_coordinator.grantRole,
        signing_coordinator.INITIATOR_ROLE(),
        deployer.get_account().address,
    )

    deployments = [
        threshold_signing_multisig_clone_factory,
        signing_coordinator,
    ]

    deployer.finalize(deployments=deployments)
