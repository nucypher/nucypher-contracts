import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape import chain, project
from ape.api import AccountAPI
from ape.cli import get_user_selected_account
from ape.contracts.base import ContractContainer, ContractInstance
from scripts.constants import NULL_ADDRESS
from scripts.utils import check_etherscan_plugin, check_infura_plugin, check_registry_filepath
from web3.auto.gethdev import w3

VARIABLE_PREFIX = "$"
PROXY_DECLARATION_DELIMETER = ":"

SPECIAL_VALUE_VARIABLES = {"EMPTY_BYTES": b""}

PROXY_NAME = "TransparentUpgradeableProxy"


def prepare_deployment(
    params_filepath: Path, registry_filepath: Path, publish: bool = False
) -> typing.Tuple[AccountAPI, "ApeDeploymentParameters"]:
    """
    Prepares the deployment by loading the deployment parameters
    and checking the pre-deployment conditions.

    NOTE: publish is False by default because we use customized artifact tracking
    that is not compatible with the ape publish command.
    """

    # pre-deployment checks
    check_registry_filepath(registry_filepath=registry_filepath)
    check_etherscan_plugin()
    check_infura_plugin()

    # load (and implicitly validate) deployment parameters
    constructor_parameters = ConstructorParameters.from_file(params_filepath)
    deployment_parameters = ApeDeploymentParameters(constructor_parameters, publish)

    # do this last so that the user can see any failed
    # pre-deployment checks or validation errors.
    deployer_account = get_user_selected_account()
    return deployer_account, deployment_parameters


def _is_proxy_variable(variable: str):
    return PROXY_DECLARATION_DELIMETER in variable


def _resolve_proxy_address(variable) -> str:
    proxy, target = variable.split(PROXY_DECLARATION_DELIMETER)
    target_contract_container = _get_contract_container(target)
    target_contract_instance = _get_contract_instance(target_contract_container)
    if target_contract_instance == NULL_ADDRESS:
        # eager validation
        return NULL_ADDRESS

    local_proxies = chain.contracts._local_proxies
    for proxy_address, proxy_info in local_proxies.items():
        if proxy_info.target == target_contract_instance.address:
            return proxy_address

    raise ConstructorParameters.Invalid(f"Could not determine proxy for {variable}")


def _is_variable(param: Any) -> bool:
    """Returns True if the param is a variable."""
    result = isinstance(param, str) and param.startswith(VARIABLE_PREFIX)
    return result


def _get_contract_instance(contract_container: ContractContainer) -> ContractInstance:
    contract_instances = contract_container.deployments
    if not contract_instances:
        return NULL_ADDRESS
    if len(contract_instances) != 1:
        raise ConstructorParameters.Invalid(
            f"Variable {contract_container.contract_type.name} is ambiguous - "
            f"expected exactly one contract instance, got {len(contract_instances)}"
        )
    contract_instance = contract_instances[0]
    return contract_instance


def _resolve_param(value: Any) -> Any:
    """Resolves a single parameter value."""
    if not _is_variable(value):
        return value  # literally a value

    variable = value.strip(VARIABLE_PREFIX)

    # special values
    if variable in SPECIAL_VALUE_VARIABLES:
        return SPECIAL_VALUE_VARIABLES[variable]

    # proxied contract
    if _is_proxy_variable(variable):
        return _resolve_proxy_address(variable)

    contract_container = _get_contract_container(variable)
    contract_instance = _get_contract_instance(contract_container)
    if contract_instance == NULL_ADDRESS:
        return NULL_ADDRESS

    return contract_instance.address


def _resolve_list(value: List[Any]) -> List[Any]:
    """Resolves a list of parameter values."""
    params = [_resolve_param(v) for v in value]
    return params


def _resolve_parameters(parameters: OrderedDict) -> OrderedDict:
    """Resolves a dictionary of parameter values for a single contract"""
    resolved_params = OrderedDict()
    for name, value in parameters.items():
        if isinstance(value, list):
            resolved_params[name] = _resolve_list(value)
        else:
            resolved_params[name] = _resolve_param(value)
    return resolved_params


def _validate_constructor_param(param: Any, contracts: List[str]) -> None:
    """Validates a single constructor parameter."""
    if not _is_variable(param):
        return  # literally a value
    variable = param.strip(VARIABLE_PREFIX)

    if _is_proxy_variable(variable):
        proxy, target = variable.split(PROXY_DECLARATION_DELIMETER)

        if proxy != PROXY_NAME:
            raise ConstructorParameters.Invalid(
                f"Ambiguous proxy variable {param}; only {PROXY_NAME} "
                f"allowed before '{PROXY_DECLARATION_DELIMETER}'"
            )

        # check proxy target
        variable = target

    if variable in SPECIAL_VALUE_VARIABLES:
        return

    if variable in contracts:
        return

    raise ConstructorParameters.Invalid(f"Variable {param} is not resolvable")


def _validate_constructor_param_list(params: List[Any], contracts: List[str]) -> None:
    """Validates a list of constructor parameters."""
    for param in params:
        _validate_constructor_param(param, contracts)


def _validate_constructor_abi_inputs(
    contract_name: str, abi_inputs: List[Any], parameters: OrderedDict
) -> None:
    """Validates the constructor parameters against the constructor ABI."""
    if len(parameters) != len(abi_inputs):
        raise ConstructorParameters.Invalid(
            f"Constructor parameters length mismatch - "
            f"{contract_name} ABI requires {len(abi_inputs)}, Got {len(parameters)}."
        )
    if not abi_inputs:
        return  # no constructor parameters

    codex = enumerate(zip(abi_inputs, parameters.items()), start=0)
    for position, (abi_input, resolved_input) in codex:
        name, value = resolved_input
        # validate name
        if abi_input.name != name:
            raise ConstructorParameters.Invalid(
                f"Constructor parameter name '{name}' at position {position} does not "
                f"match the expected ABI name '{abi_input.name}'"
            )

        # validate value type
        value_to_validate = value
        if _is_variable(value):
            if isinstance(value, list):
                value_to_validate = _resolve_list(value)
            else:
                value_to_validate = _resolve_param(value)
        if not w3.is_encodable(abi_input.type, value_to_validate):
            raise ConstructorParameters.Invalid(
                f"Constructor param name '{name}' at position {position} has a value '{value}' "
                f"whose type does not match expected ABI type '{abi_input.type}'"
            )


def _get_dependency_contract_container(contract: str) -> ContractContainer:
    for dependency_name, dependency_versions in project.dependencies.items():
        if len(dependency_versions) > 1:
            raise ValueError(f"Ambiguous {dependency_name} dependency for {contract}")
        try:
            dependency_api = list(dependency_versions.values())[0]
            contract_container = getattr(dependency_api, contract)
            return contract_container
        except AttributeError:
            continue

    raise ValueError(f"No contract found for {contract}")


def _get_contract_container(contract: str) -> ContractContainer:
    try:
        contract_container = getattr(project, contract)
    except AttributeError:
        # not in root project; check dependencies
        contract_container = _get_dependency_contract_container(contract)

    return contract_container


def validate_constructor_parameters(config: typing.OrderedDict[str, Any]) -> None:
    """Validates the constructor parameters for all contracts in a single config."""
    available_contracts = list(config.keys())
    for contract, parameters in config.items():
        for name, value in parameters.items():
            if isinstance(value, list):
                _validate_constructor_param_list(value, available_contracts)
            else:
                _validate_constructor_param(value, available_contracts)

        contract_container = _get_contract_container(contract)
        _validate_constructor_abi_inputs(
            contract_name=contract,
            abi_inputs=contract_container.constructor.abi.inputs,
            parameters=parameters,
        )


def _confirm_deployment(contract_name: str) -> None:
    """Asks the user to confirm the deployment of a single contract."""
    answer = input(f"Deploy {contract_name} Y/N? ")
    if answer.lower().strip() == "n":
        print("Aborting deployment!")
        exit(-1)


def _confirm_null_address() -> None:
    answer = input("Null Address detected for deployment parameter; Continue? Y/N? ")
    if answer.lower().strip() == "n":
        print("Aborting deployment!")
        exit(-1)


def _confirm_resolution(resolved_params: OrderedDict, contract_name: str) -> None:
    """Asks the user to confirm the resolved constructor parameters for a single contract."""
    if len(resolved_params) == 0:
        print(f"\n(i) No constructor parameters for {contract_name}")
        _confirm_deployment(contract_name)
        return

    print(f"\nConstructor parameters for {contract_name}")
    contains_null_address = False
    for name, resolved_value in resolved_params.items():
        print(f"\t{name}={resolved_value}")
        if not contains_null_address:
            contains_null_address = resolved_value == NULL_ADDRESS
    _confirm_deployment(contract_name)
    if contains_null_address:
        _confirm_null_address()


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

    def resolve(self, contract_name: str) -> OrderedDict:
        """Resolves the constructor parameters for a single contract."""
        result = _resolve_parameters(self.parameters[contract_name])
        return result


class ApeDeploymentParameters:
    """Represents ape deployment parameters for a set of contracts."""

    def __init__(self, constructor_parameters: ConstructorParameters, publish: bool):
        self.constructor_parameters = constructor_parameters
        self.publish = publish

    def get_kwargs(self) -> typing.Dict[str, Any]:
        """Returns the deployment kwargs."""
        return {"publish": self.publish}

    def get(self, container: ContractContainer) -> List[Any]:
        """Resolves the deployment parameters for a single contract."""
        contract_name = container.contract_type.name
        resolved_constructor_params = self.constructor_parameters.resolve(contract_name)
        _confirm_resolution(resolved_constructor_params, contract_name)
        deployment_params = [container, *resolved_constructor_params.values()]
        return deployment_params
