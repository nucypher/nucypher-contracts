import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

VARIABLE_PREFIX = "$"


class DeploymentConfigError(ValueError):
    pass


def read_deployment_config(config_filepath: Path) -> typing.OrderedDict[str, Any]:
    with open(config_filepath, "r") as config_file:
        config = json.load(config_file)
        return OrderedDict(config)


def is_variable(param: Any):
    return isinstance(param, str) and param.startswith(VARIABLE_PREFIX)


def _validate_param(param: Any, contracts: List[str]):
    if not is_variable(param):
        return

    variable = param.strip(VARIABLE_PREFIX)
    if variable not in contracts:
        raise DeploymentConfigError(f"Variable {param} is not resolvable")


def validate_deployment_config(config: typing.OrderedDict[str, Any]):
    available_contracts = list(config.keys())

    for contract, parameters in config.items():
        for name, value in parameters.items():
            if isinstance(value, list):
                for param in value:
                    _validate_param(param, available_contracts)
            else:
                _validate_param(value, available_contracts)
