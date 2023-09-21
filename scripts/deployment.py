import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape.api import AccountAPI
from ape.cli import get_user_selected_account
from ape.contracts.base import ContractContainer
from scripts.utils import check_etherscan_plugin, check_registry_filepath

VARIABLE_PREFIX = "$"


def prepare_deployment(
    params_filepath: Path,
    registry_filepath: Path,
    publish: bool
) -> typing.Tuple[AccountAPI, "ApeDeploymentParameters"]:
    """
    Prepares the deployment by loading the deployment parameters
    and checking the pre-deployment conditions.
    """

    # pre-deployment checks
    check_registry_filepath(registry_filepath=registry_filepath)
    check_etherscan_plugin()
    deployer_account = get_user_selected_account()

    # load deployment parameters
    constructor_parameters = ConstructorParameters.from_file(params_filepath)
    deployment_parameters = ApeDeploymentParameters(constructor_parameters, publish)

    return deployer_account, deployment_parameters


def _is_variable(param: Any) -> bool:
    """Returns True if the param is a variable."""
    result = isinstance(param, str) and param.startswith(VARIABLE_PREFIX)
    return result


def _resolve_param(
        value: Any,
        context: typing.Dict[str, Any]
) -> Any:
    """Resolves a single parameter value."""
    if not _is_variable(value):
        return value  # literally a value
    variable = value.strip(VARIABLE_PREFIX)
    contract_instance = context[variable]
    return contract_instance.address


def _resolve_list(
        value: List[Any],
        context: typing.Dict[str, Any]
) -> List[Any]:
    """Resolves a list of parameter values."""
    params = [_resolve_param(v, context) for v in value]
    return params


def _resolve_parameters(
        parameters: OrderedDict,
        context: typing.Dict[str, Any]
) -> OrderedDict:
    """Resolves a dictionary of parameter values for a single contract"""
    resolved_params = OrderedDict()
    for name, value in parameters.items():
        if isinstance(value, list):
            resolved_params[name] = _resolve_list(value, context)
        else:
            resolved_params[name] = _resolve_param(value, context)
    return resolved_params


def _validate_constructor_param(
        param: Any,
        contracts: List[str]
) -> None:
    """Validates a single constructor parameter."""
    if not _is_variable(param):
        return  # literally a value
    variable = param.strip(VARIABLE_PREFIX)
    if variable not in contracts:
        raise ConstructorParameters.Invalid(f"Variable {param} is not resolvable")


def _validate_constructor_param_list(
        params: List[Any],
        contracts: List[str]
) -> None:
    """Validates a list of constructor parameters."""
    for param in params:
        _validate_constructor_param(param, contracts)


def validate_constructor_parameters(
        config: typing.OrderedDict[str, Any]
) -> None:
    """Validates the constructor parameters for all contracts in a single config."""
    available_contracts = list(config.keys())
    for contract, parameters in config.items():
        for name, value in parameters.items():
            if isinstance(value, list):
                _validate_constructor_param_list(value, available_contracts)
            else:
                _validate_constructor_param(value, available_contracts)


def _confirm_deployment(contract_name: str) -> None:
    """Asks the user to confirm the deployment of a single contract."""
    answer = input(f"Deploy {contract_name} Y/N? ")
    if answer.lower().strip() == "n":
        print("Aborting deployment!")
        exit(-1)


def _confirm_resolution(
        resolved_params: OrderedDict,
        contract_name: str
) -> None:
    """Asks the user to confirm the resolved constructor parameters for a single contract."""
    if len(resolved_params) == 0:
        print(f"(i) No constructor parameters for {contract_name}")
        _confirm_deployment(contract_name)
        return

    print(f"Constructor parameters for {contract_name}")
    for name, resolved_value in resolved_params.items():
        print(f"\t{name}={resolved_value}")
    _confirm_deployment(contract_name)


class ConstructorParameters:
    """Represents the constructor parameters for a set of contracts."""

    class Invalid(Exception):
        """Raised when the constructor parameters are invalid"""

    def __init__(self, parameters: OrderedDict):
        validate_constructor_parameters(parameters)
        self.parameters = parameters

    @classmethod
    def from_file(cls, filepath: Path) -> "ConstructorParameters":
        """Loads the constructor parameters from a JSON file."""
        with open(filepath, "r") as params_file:
            config = OrderedDict(json.load(params_file))
        return cls(config)

    def resolve(self, contract_name: str, context: typing.Dict[str, Any]) -> OrderedDict:
        """Resolves the constructor parameters for a single contract."""
        result = _resolve_parameters(self.parameters[contract_name], context)
        return result


class ApeDeploymentParameters:
    """Represents ape deployment parameters for a set of contracts."""

    def __init__(self, constructor_parameters: ConstructorParameters, publish: bool):
        self.constructor_parameters = constructor_parameters
        self.publish = publish

    def get_kwargs(self) -> typing.Dict[str, Any]:
        """Returns the deployment kwargs."""
        return {"publish": self.publish}

    def get(
        self, container: ContractContainer, context: typing.Dict[str, Any]
    ) -> List[Any]:
        """Resolves the deployment parameters for a single contract."""
        contract_name = container.contract_type.name
        resolved_constructor_params = self.constructor_parameters.resolve(contract_name, context)
        _confirm_resolution(resolved_constructor_params, contract_name)
        deployment_params = [container, *resolved_constructor_params.values()]
        return deployment_params
