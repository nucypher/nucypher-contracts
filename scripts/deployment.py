import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape.api import AccountAPI
from ape.cli import get_user_selected_account
from ape.contracts.base import ContractContainer
from scripts.utils import check_etherscan_plugin

VARIABLE_PREFIX = "$"


def prepare_deployment(
    params_filepath: Path, publish: bool
) -> typing.Tuple[AccountAPI, "ApeDeploymentParameters"]:
    check_etherscan_plugin()
    deployer = get_user_selected_account()

    constructor_parameters = ConstructorParameters.from_file(params_filepath)
    deployment_parameters = ApeDeploymentParameters(constructor_parameters, publish)

    return deployer, deployment_parameters


def _is_variable(param: Any) -> bool:
    return isinstance(param, str) and param.startswith(VARIABLE_PREFIX)


def _resolve_param(value: Any, context: typing.Dict[str, Any]) -> Any:
    if not _is_variable(value):
        return value
    variable = value.strip(VARIABLE_PREFIX)
    contract_instance = context[variable]
    return contract_instance.address


def _validate_constructor_param(param: Any, contracts: List[str]) -> None:
    if not _is_variable(param):
        return
    variable = param.strip(VARIABLE_PREFIX)
    if variable not in contracts:
        raise ConstructorParameters.Invalid(f"Variable {param} is not resolvable")


def validate_constructor_parameters(config: typing.OrderedDict[str, Any]) -> None:
    available_contracts = list(config.keys())
    for contract, parameters in config.items():
        for name, value in parameters.items():
            if isinstance(value, list):
                for param in value:
                    _validate_constructor_param(param, available_contracts)
            else:
                _validate_constructor_param(value, available_contracts)


def _confirm_resolution(resolved_params: OrderedDict, contract_name: str) -> None:
    if len(resolved_params) == 0:
        # Nothing really to confirm
        print(f"(i) No constructor parameters for {contract_name}; proceeding")
        return

    print(f"Constructor parameters for {contract_name}")
    for name, resolved_value in resolved_params.items():
        print(f"\t{name}={resolved_value}")
    answer = input("Deploy Y/N? ")
    if answer.lower().strip() == "n":
        print("Aborting deployment!")
        exit(-1)


class ConstructorParameters:
    class Invalid(Exception):
        """Raised when the constructor parameters are invalid"""

    def __init__(self, parameters: OrderedDict):
        validate_constructor_parameters(parameters)
        self.parameters = parameters

    @classmethod
    def from_file(cls, params_filepath: Path) -> "ConstructorParameters":
        with open(params_filepath, "r") as params_file:
            config = OrderedDict(json.load(params_file))
        return cls(config)

    def resolve(self, contract_name: str, context: typing.Dict[str, Any]) -> OrderedDict:
        resolved_params = OrderedDict()
        for name, value in self.parameters[contract_name].items():
            if isinstance(value, list):
                param_value_list = list()
                for item in value:
                    param = _resolve_param(item, context)
                    param_value_list.append(param)
                resolved_params[name] = param_value_list
            else:
                resolved_params[name] = _resolve_param(value, context)
        return resolved_params


class ApeDeploymentParameters:
    def __init__(self, constructor_parameters: ConstructorParameters, publish: bool):
        self.constructor_parameters = constructor_parameters
        self.publish = publish

    def get_kwargs(self):
        return {"publish": self.publish}

    def get(self, *args, **kwargs):
        return self.__resolve_deployment_parameters(*args, **kwargs)

    def __resolve_deployment_parameters(
        self, container: ContractContainer, context: typing.Dict[str, Any], interactive: bool = True
    ) -> List[Any]:
        contract_name = container.contract_type.name
        resolved_params = self.constructor_parameters.resolve(contract_name, context)
        if interactive:
            _confirm_resolution(resolved_params, contract_name)

        return [container, *resolved_params.values()]
