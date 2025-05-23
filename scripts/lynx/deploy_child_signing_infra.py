#!/usr/bin/python3
from pathlib import Path

import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Deployer
from deployment.registry import contracts_from_registry

VERIFY = False


@click.command(cls=ConnectedProviderCommand)
@network_option(required=True)
@click.option(
    "--constructor-params-filepath",
    "-f",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    help="Constructor params filepath",
    required=True,
)
def cli(network, constructor_params_filepath):
    """
    This script deploys the Signing Infrastructure on the relevant L2 chain.
    It can be reused for different child chains by providing the relevant constructor params file.
    """
    deployer = Deployer.from_yaml(filepath=constructor_params_filepath, verify=VERIFY)
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "lynx.json", chain_id=11155111)
    dispatcher = instances[project.SigningCoordinatorDispatcher.contract_type.name]

    # deploy bridge contracts
    with networks.ethereum.sepolia.use_provider("infura"):
        # L1 sender belongs on the root chain
        l1_sender = deployer.deploy(project.OpL1Sender)

    l2_receiver = deployer.deploy(project.OpL2Receiver)

    deployer.transact(l1_sender.initialize, l2_receiver.address)

    # deploy child contracts
    signing_coordinator_child = deployer.deploy(project.SigningCoordinatorChild)

    _ = deployer.deploy(project.ThresholdSigningMultisig)
    signing_multisig_clone_factory = deployer.deploy(project.ThresholdSigningMultisigCloneFactory)

    # for root allowed caller is the dispatcher (i.e. direct call)
    deployer.transact(
        signing_coordinator_child.initialize,
        signing_multisig_clone_factory.address,
        dispatcher.address,
    )

    # register bridge contracts with dispatcher
    child_chain_id = networks.active_provider.chain_id
    with networks.ethereum.sepolia.use_provider("infura"):
        # register with the dispatcher
        deployer.transact(
            dispatcher.register,
            child_chain_id,
            l1_sender.address,
            signing_coordinator_child.address,
        )

    deployments = [
        l1_sender,
        l2_receiver,
        signing_coordinator_child,
        signing_multisig_clone_factory,
        signing_coordinator_child,
        signing_multisig_clone_factory,
    ]

    deployer.finalize(deployments=deployments)


if __name__ == "__main__":
    cli()
