#!/usr/bin/python3
from pathlib import Path

import click
from ape import networks, project
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import ARTIFACTS_DIR
from deployment.params import Deployer
from deployment.registry import (
    contracts_from_registry,
    merge_registries,
    registry_from_ape_deployments,
)

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
    instances = contracts_from_registry(filepath=ARTIFACTS_DIR / "mainnet.json", chain_id=1)
    dispatcher = instances[project.SigningCoordinatorDispatcher.contract_type.name]

    # deploy bridge contracts
    with networks.ethereum.mainnet.use_provider("infura"):
        # L1 sender belongs on the root chain
        l1_sender = deployer.deploy(project.OpL1Sender)

    l2_receiver = deployer.deploy(project.OpL2Receiver)
    deployer.transact(l2_receiver.initialize, l1_sender.address)

    with networks.ethereum.mainnet.use_provider("infura"):
        deployer.transact(l1_sender.initialize, l2_receiver.address)

    # deploy child contracts
    signing_coordinator_child = deployer.deploy(project.SigningCoordinatorChild)

    _ = deployer.deploy(project.ThresholdSigningMultisig)
    signing_multisig_clone_factory = deployer.deploy(project.ThresholdSigningMultisigCloneFactory)

    # for child allowed caller is the l2 receiver
    deployer.transact(
        signing_coordinator_child.initialize,
        signing_multisig_clone_factory.address,
        l2_receiver.address,
    )

    # transfer ownership to NuCo multisig
    # deployer.transact(
    #     signing_coordinator_child.transferOwnership, deployer.constants.NUCO_MULTISIG
    # )

    # register bridge contracts with dispatcher
    child_chain_id = networks.active_provider.chain_id
    with networks.ethereum.mainnet.use_provider("infura"):
        # register with the dispatcher
        deployer.transact(
            dispatcher.register,
            child_chain_id,
            l1_sender.address,
            signing_coordinator_child.address,
        )

        # store l1 sender deployment
        l1_deployments = [l1_sender]
        l1_temp_registry_filepath = (
            deployer.registry_filepath.parent
            / deployer.registry_filepath.name.replace(".json", "_l1.json")
        )
        registry_from_ape_deployments(
            deployments=l1_deployments, output_filepath=l1_temp_registry_filepath
        )

    # base deployments
    deployments = [
        l2_receiver,
        signing_coordinator_child,
        signing_multisig_clone_factory,
    ]
    deployer.finalize(deployments=deployments)

    # merge both for a single registry
    merge_registries(
        deployer.registry_filepath, l1_temp_registry_filepath, deployer.registry_filepath
    )

    # remove l1 deployment file
    l1_temp_registry_filepath.unlink()


if __name__ == "__main__":
    cli()
