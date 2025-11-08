#!/usr/bin/python3

from ape import chain, project
from eth.constants import ZERO_ADDRESS

from deployment.constants import ARTIFACTS_DIR, CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx" / "redeploy-root-signing-infra.yml"


def main():
    """
    This script redeploys SigningCoordinator and Dispatcher on Lynx/Sepolia.
    """

    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=VERIFY)

    # deploy root contracts
    signing_coordinator = deployer.deploy(project.SigningCoordinator)

    signing_coordinator_dispatcher = deployer.deploy(project.SigningCoordinatorDispatcher)

    deployer.transact(
        signing_coordinator.initialize,
        deployer.constants.HALF_HOUR_IN_SECONDS,
        deployer.constants.MAX_DKG_SIZE,
        signing_coordinator_dispatcher.address,
        deployer.get_account().address,
    )
    deployer.transact(
        signing_coordinator.grantRole,
        signing_coordinator.INITIATOR_ROLE(),
        deployer.get_account().address,
    )

    existing_deployments = contracts_from_registry(
        filepath=ARTIFACTS_DIR / "lynx.json", chain_id=chain.provider.chain_id
    )
    signing_coordinator_child = existing_deployments[
        project.SigningCoordinatorChild.contract_type.name
    ]

    # for root allowed caller is the dispatcher (i.e. direct call)
    deployer.transact(
        signing_coordinator_child.setAllowedCaller,
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

    new_deployments = [
        signing_coordinator,
        signing_coordinator_dispatcher,
    ]

    deployer.finalize(deployments=new_deployments)
