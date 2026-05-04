#!/usr/bin/python3
from pathlib import Path

import click
from ape import project
from ape.cli import ConnectedProviderCommand, network_option

from deployment.constants import ARTIFACTS_DIR, SUPPORTED_TACO_DOMAINS
from deployment.params import Deployer
from deployment.registry import contracts_from_registry, merge_registries

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
@click.option(
    "--domain",
    "-d",
    help="TACo domain",
    type=click.Choice(SUPPORTED_TACO_DOMAINS),
    required=True,
)
def cli(network, constructor_params_filepath, domain):
    """
    This script updates the MultisigFactory contract used by SigningCoordinatorChild.
    It can be reused for different chains by providing the relevant constructor params
    file and domain values.
    """
    deployer = Deployer.from_yaml(filepath=constructor_params_filepath, verify=VERIFY)
    registry_filepath = ARTIFACTS_DIR / f"{domain}.json"
    chain_id = deployer.config["deployment"]["chain_id"]

    instances = contracts_from_registry(filepath=registry_filepath, chain_id=chain_id)
    signing_coordinator_child = instances[project.SigningCoordinatorChild.contract_type.name]

    assert signing_coordinator_child.address == deployer.constants.SIGNING_COORDINATOR_CHILD, (
        f"Incorrect child contract address; expected {signing_coordinator_child.address} "
        f"but got {deployer.constants.SIGNING_COORDINATOR_CHILD}"
    )

    _ = deployer.deploy(project.ThresholdSigningMultisig)
    signing_multisig_clone_factory = deployer.deploy(project.ThresholdSigningMultisigCloneFactory)

    # set updated multisig factory
    deployer.transact(
        signing_coordinator_child.setMultisigFactory,
        signing_multisig_clone_factory.address,
    )

    deployments = [
        signing_multisig_clone_factory,
    ]
    deployer.finalize(deployments=deployments)

    merge_registries(
        registry_1_filepath=registry_filepath,
        registry_2_filepath=deployer.registry_filepath,
        output_filepath=registry_filepath,
    )


if __name__ == "__main__":
    cli()
