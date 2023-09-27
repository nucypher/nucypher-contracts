import json
import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape import chain, project
from ape.api import AccountAPI
from ape.contracts.base import (
    ContractContainer,
    ContractInstance
)
from ape.utils import ZERO_ADDRESS
from eth_typing import ChecksumAddress
from web3.auto.gethdev import w3

from deployment.confirm import _confirm_resolution
from deployment.constants import (
    VARIABLE_PREFIX,
    SPECIAL_VARIABLE_DELIMITER,
    PROXY_NAME,
    BYTES_PREFIX,
    HEX_PREFIX,
    DEPLOYER_INDICATOR
)


def _is_variable(param: Any) -> bool:
    """Returns True if the param is a variable."""
    result = isinstance(param, str) and param.startswith(VARIABLE_PREFIX)
    return result


def _is_special_variable(variable: str) -> bool:
    """Returns True if the variable is a special variable."""
    rules = [
        _is_bytes(variable),
        _is_proxy_variable(variable),
        _is_deployer(variable)
    ]
    return any(rules)


def _is_proxy_variable(variable: str) -> bool:
    """Returns True if the variable is a special proxy variable."""
    return variable.startswith(PROXY_NAME + SPECIAL_VARIABLE_DELIMITER)


def _is_bytes(variable: str) -> bool:
    """Returns True if the variable is a special bytes value."""
    return variable.startswith(BYTES_PREFIX + SPECIAL_VARIABLE_DELIMITER)


def _is_deployer(variable: str) -> bool:
    """Returns True if the variable is a special deployer variable."""
    return variable == DEPLOYER_INDICATOR


def _resolve_proxy_address(variable) -> str:
    proxy, target = variable.split(SPECIAL_VARIABLE_DELIMITER)
    target_contract_container = get_contract_container(target)
    target_contract_instance = _get_contract_instance(target_contract_container)
    if target_contract_instance == ZERO_ADDRESS:
        # eager validation
        return ZERO_ADDRESS

    local_proxies = chain.contracts._local_proxies
    for proxy_address, proxy_info in local_proxies.items():
        if proxy_info.target == target_contract_instance.address:
            return proxy_address

    raise ConstructorParameters.Invalid(f"Could not determine proxy for {variable}")


def _resolve_bytes(variable: str) -> bytes:
    """Resolves a special bytes value."""
    _prefix, value = variable.split(SPECIAL_VARIABLE_DELIMITER)
    if not value.startswith(HEX_PREFIX):
        raise ConstructorParameters.Invalid(f"Invalid bytes value {variable}")
    value = bytes.fromhex(value[2:])
    return value


def _get_contract_instance(contract_container: ContractContainer) -> typing.Union[ContractInstance, ChecksumAddress]:
    contract_instances = contract_container.deployments
    if not contract_instances:
        return ZERO_ADDRESS
    if len(contract_instances) != 1:
        raise ConstructorParameters.Invalid(
            f"Variable {contract_container.contract_type.name} is ambiguous - "
            f"expected exactly one contract instance, got {len(contract_instances)}"
        )
    contract_instance = contract_instances[0]
    return contract_instance


def _resolve_deployer() -> str:
    deployer_account = Deployer.get_account()
    if deployer_account is None:
        return ZERO_ADDRESS
    else:
        return deployer_account.address


def _resolve_contract_address(variable: str) -> str:
    """Resolves a contract address."""
    contract_container = get_contract_container(variable)
    contract_instance = _get_contract_instance(contract_container)
    if contract_instance == ZERO_ADDRESS:
        return ZERO_ADDRESS
    return contract_instance.address


def _resolve_special_variable(variable: str) -> Any:
    if _is_bytes(variable):
        result = _resolve_bytes(variable)
    elif _is_proxy_variable(variable):
        result = _resolve_proxy_address(variable)
    elif _is_deployer(variable):
        result = _resolve_deployer()
    else:
        raise ValueError(f"Invalid special variable {variable}")
    return result


def _resolve_param(value: Any) -> Any:
    """Resolves a single parameter value."""
    if not _is_variable(value):
        return value  # literally a value
    variable = value.strip(VARIABLE_PREFIX)
    if _is_special_variable(variable):
        result = _resolve_special_variable(variable)
    else:
        result = _resolve_contract_address(variable)
    return result


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
        proxy, target = variable.split(SPECIAL_VARIABLE_DELIMITER)
        if proxy != PROXY_NAME:
            raise ConstructorParameters.Invalid(
                f"Ambiguous proxy variable {param}; only {PROXY_NAME} "
                f"allowed before '{SPECIAL_VARIABLE_DELIMITER}'"
            )
        variable = target  # check proxy target

    if _is_special_variable(variable):
        return  # special variables are always marked as valid

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


def get_contract_container(contract: str) -> ContractContainer:
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

        contract_container = get_contract_container(contract)
        _validate_constructor_abi_inputs(
            contract_name=contract,
            abi_inputs=contract_container.constructor.abi.inputs,
            parameters=parameters,
        )


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


class Deployer:
    """
    Represents ape an ape deployment account plus
    deployment parameters for a set of contracts.
    """

    __DEPLOYER_ACCOUNT: AccountAPI = None

    def __init__(self, account: AccountAPI, params_path: Path, publish: bool):
        self.constructor_parameters = ConstructorParameters.from_file(params_path)
        self._set_deployer(account)
        self.publish = publish

    @classmethod
    def get_account(cls) -> AccountAPI:
        """Returns the deployer account."""
        return cls.__DEPLOYER_ACCOUNT

    @classmethod
    def _set_deployer(cls, deployer: AccountAPI) -> None:
        """Sets the deployer account."""
        cls.__DEPLOYER_ACCOUNT = deployer

    def _get_kwargs(self) -> typing.Dict[str, Any]:
        """Returns the deployment kwargs."""
        return {"publish": self.publish}

    def _get_args(self, container: ContractContainer) -> List[Any]:
        """Resolves the deployment parameters for a single contract."""
        contract_name = container.contract_type.name
        resolved_constructor_params = self.constructor_parameters.resolve(contract_name)
        _confirm_resolution(resolved_constructor_params, contract_name)
        deployment_params = [container, *resolved_constructor_params.values()]
        return deployment_params

    def deploy(self, container: ContractContainer) -> ContractInstance:
        deployer_account = self.get_account()
        args, kwargs = self._get_args(container), self._get_kwargs()
        instance = deployer_account.deploy(*args, **kwargs)
        return instance
