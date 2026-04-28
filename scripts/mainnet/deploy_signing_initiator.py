#!/usr/bin/python3

from ape import project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "signing-initiator.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    signing_cohort_initiator = deployer.deploy(project.SigningCohortInitiator)

    # set parameters
    deployer.transact(
        signing_cohort_initiator.setFeeRates,
        deployer.constants.INIT_FEE_RATE_PER_SECOND_WEI,
        deployer.constants.EXTEND_FEE_RATE_PER_SECOND_WEI,
    )
    deployer.transact(
        signing_cohort_initiator.setDefaultParameters,
        deployer.constants.DEFAULT_PROVIDERS,
        deployer.constants.DEFAULT_THRESHOLD,
        deployer.constants.DEFAULT_COHORT_DURATION,
    )

    # transfer ownership
    deployer.transact(signing_cohort_initiator.transferOwnership, deployer.constants.NUCO_MULTISIG)

    deployments = [
        signing_cohort_initiator,
    ]

    deployer.finalize(deployments=deployments)
