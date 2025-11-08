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
    This script updates the Signing Infrastructure on the relevant L2 chain.
    It can be reused for different child chains by providing the relevant constructor params file.
    """
    deployer = Deployer.from_yaml(filepath=constructor_params_filepath, verify=VERIFY)
    sepolia_instances = contracts_from_registry(
        filepath=ARTIFACTS_DIR / "lynx.json", chain_id=11155111
    )
    dispatcher = sepolia_instances[project.SigningCoordinatorDispatcher.contract_type.name]

    # deploy bridge contracts
    with networks.ethereum.sepolia.use_provider("infura"):
        # L1 sender belongs on the root chain
        l1_sender = deployer.deploy(project.OpL1Sender)

    l2_receiver = deployer.deploy(project.OpL2Receiver)
    deployer.transact(l2_receiver.initialize, l1_sender.address)

    with networks.ethereum.sepolia.use_provider("infura"):
        deployer.transact(l1_sender.initialize, l2_receiver.address)

    # update child contracts
    child_chain_id = networks.active_provider.chain_id

    child_instances = contracts_from_registry(
        filepath=ARTIFACTS_DIR / "lynx.json", chain_id=child_chain_id
    )
    signing_coordinator_child = child_instances[project.SigningCoordinatorChild.contract_type.name]

    # for child allowed caller is the l2 receiver
    deployer.transact(
        signing_coordinator_child.setAllowedCaller,
        l2_receiver.address,
    )

    # register bridge contracts with dispatcher
    with networks.ethereum.sepolia.use_provider("infura"):
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
