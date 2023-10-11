#!/usr/bin/python3
from pathlib import Path

import click
from deployment.registry import merge_registries


@click.command()
@click.option(
    "--registry-1",
    help="Filepath to registry file 1",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--registry-2",
    help="Filepath to registry file 2",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--output-registry",
    "-o",
    help="Filepath of output registry file",
    type=click.Path(dir_okay=False, exists=False, path_type=Path),
    required=True,
)
@click.option(
    "--deprecated-contract",
    "-d",
    "deprecated_contracts",
    help="Names of any deprecated contracts to exclude from the merge",
    required=False,
    multiple=True,
)
def cli(registry_1, registry_2, output_registry, deprecated_contracts):
    """Merge two registry entries into one."""
    merge_registries(
        registry_1_filepath=registry_1,
        registry_2_filepath=registry_2,
        output_filepath=output_registry,
        deprecated_contracts=deprecated_contracts,
    )
