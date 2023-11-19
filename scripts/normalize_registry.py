#!/usr/bin/python3
from pathlib import Path

import click
from deployment.registry import normalize_registry


@click.command()
@click.option(
    "--registry",
    help="Filepath to registry file",
    type=click.Path(dir_okay=False, exists=True, path_type=Path),
    required=True,
)
def cli(registry):
    """Normalize registry file"""
    normalize_registry(registry)
