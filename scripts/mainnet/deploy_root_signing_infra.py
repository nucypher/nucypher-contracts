#!/usr/bin/python3

from ape import chain, project
from eth.constants import ZERO_ADDRESS

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "root-signing-infra.yml"


def main():
    """
    This script deploys the Signing Infrastructure on Mainnet/Ethereum.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # deploy root contracts
    signing_coordinator = deployer.deploy(project.SigningCoordinator)

    signing_coordinator_dispatcher = deployer.deploy(project.SigningCoordinatorDispatcher)

    deployer.transact(
        signing_coordinator.initialize,
        deployer.constants.SIGNING_RITUAL_TIMEOUT_SECONDS,
        deployer.constants.MAX_COHORT_SIZE,
        signing_coordinator_dispatcher.address,
        deployer.constants.NUCO_MULTISIG,
    )

    # deploy child contracts on same root chain (ethereum mainnet)
    signing_coordinator_child = deployer.deploy(project.SigningCoordinatorChild)

    _ = deployer.deploy(project.ThresholdSigningMultisig)
    signing_multisig_clone_factory = deployer.deploy(project.ThresholdSigningMultisigCloneFactory)

    # for root allowed caller is the dispatcher (i.e. direct call)
    deployer.transact(
        signing_coordinator_child.initialize,
        signing_multisig_clone_factory.address,
        signing_coordinator_dispatcher.address,
    )

    # register the child contract to be called directly on L1 by dispatcher,
    # without L1 sender
    deployer.transact(
        signing_coordinator_dispatcher.register,
        chain.provider.chain_id,
        ZERO_ADDRESS,
        signing_coordinator_child.address,
    )

    # transfer ownership to NuCo multisig
    deployer.transact(
        signing_coordinator_dispatcher.transferOwnership, deployer.constants.NUCO_MULTISIG
    )
    deployer.transact(signing_coordinator_child.transferOwnership, deployer.constants.NUCO_MULTISIG)

    # write to registry
    deployments = [
        signing_coordinator,
        signing_coordinator_dispatcher,
        signing_coordinator_child,
        signing_multisig_clone_factory,
    ]

    deployer.finalize(deployments=deployments)
