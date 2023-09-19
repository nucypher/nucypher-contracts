import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape.contracts.base import ContractContainer

VARIABLE_PREFIX = "$"


class DeploymentConfigError(ValueError):
    pass


def is_variable(param: Any) -> bool:
    return isinstance(param, str) and param.startswith(VARIABLE_PREFIX)


def _resolve_param(value: Any, context: typing.Dict[str, Any]) -> Any:
    if not is_variable(value):
        return value
    variable = value.strip(VARIABLE_PREFIX)
    contract_instance = context[variable]
    return contract_instance.address


def _resolve_parameters(
        parameters: OrderedDict,
        context: typing.Dict[str, Any]
) -> OrderedDict:
    resolved_params = OrderedDict()
    for name, value in parameters.items():
        if isinstance(value, list):
            param_value_list = list()
            for item in value:
                param = _resolve_param(item, context)
                param_value_list.append(param)
            resolved_params[name] = param_value_list
        else:
            resolved_params[name] = _resolve_param(value, context)
    return resolved_params


def _validate_param(
        param: Any,
        contracts: List[str]
) -> None:
    if not is_variable(param):
        return
    variable = param.strip(VARIABLE_PREFIX)
    if variable not in contracts:
        raise DeploymentConfigError(f"Variable {param} is not resolvable")


def validate_deployment_config(
        config: typing.OrderedDict[str, Any]
) -> None:
    available_contracts = list(config.keys())
    for contract, parameters in config.items():
        for name, value in parameters.items():
            if isinstance(value, list):
                for param in value:
                    _validate_param(param, available_contracts)
            else:
                _validate_param(value, available_contracts)


def _confirm_resolution(
        resolved_params: OrderedDict,
        contract_name: str
) -> None:
    print(f"Resolved constructor parameters for {contract_name}")
    for name, resolved_value in resolved_params:
        print(f"\t{name}={resolved_value}")
    answer = input("Continue Y/N? ")
    if answer.lower().strip() == "n":
        print("Aborting deployment!")
        exit(-1)


class ConstructorParams:
    def __init__(self, constructor_values: OrderedDict):
        self.params = constructor_values

    @classmethod
    def from_file(cls, config_filepath: Path) -> "ConstructorParams":
        with open(config_filepath, "r") as config_file:
            config = OrderedDict(json.load(config_file))
        return cls(config)

    def get_params(
        self,
        container: ContractContainer,
        context: typing.Dict[str, Any],
        interactive: bool = True
    ) -> List[Any]:
        contract_name = container.contract_type.name
        contract_parameters = self.params[contract_name]
        resolved_params = _resolve_parameters(
            contract_parameters,
            context,
        )
        if interactive:
            _confirm_resolution(
                resolved_params,
                contract_name
            )
        return list(resolved_params.values())
