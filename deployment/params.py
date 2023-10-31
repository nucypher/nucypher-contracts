import typing
from collections import OrderedDict
from pathlib import Path
from typing import Any, List

from ape import chain, networks
from ape.api import AccountAPI, ReceiptAPI
from ape.cli import get_user_selected_account
from ape.contracts.base import ContractContainer, ContractInstance, ContractTransactionHandler
from ape.utils import ZERO_ADDRESS
from eth_typing import ChecksumAddress
from web3.auto.gethdev import w3

from deployment.confirm import _confirm_resolution, _continue
from deployment.constants import (
    BYTES_PREFIX,
    DEPLOYER_INDICATOR,
    PROXY_NAME,
    SPECIAL_VARIABLE_DELIMITER,
    VARIABLE_PREFIX,
)
from deployment.registry import registry_from_ape_deployments
from deployment.utils import (
    _load_yaml,
    check_plugins,
    get_contract_container,
    validate_config,
    verify_contracts,
)


def _is_variable(param: Any) -> bool:
    """Returns True if the param is a variable."""
    result = isinstance(param, str) and param.startswith(VARIABLE_PREFIX)
    return result


def _is_special_variable(variable: str) -> bool:
    """Returns True if the variable is a special variable."""
    rules = [_is_bytes, _is_proxy_variable, _is_deployer, _is_constant]
    return any(rule(variable) for rule in rules)


def _is_proxy_variable(variable: str) -> bool:
    """Returns True if the variable is a special proxy variable."""
    return variable.startswith(PROXY_NAME + SPECIAL_VARIABLE_DELIMITER)


def _is_bytes(variable: str) -> bool:
    """Returns True if the variable is a special bytes value."""
    return variable.startswith(BYTES_PREFIX + SPECIAL_VARIABLE_DELIMITER)


def _is_deployer(variable: str) -> bool:
    """Returns True if the variable is a special deployer variable."""
    return variable == DEPLOYER_INDICATOR


def _is_constant(variable: str) -> bool:
    """Returns True if the variable is a deployment constant."""
    return variable.isupper()


def _resolve_proxy_address(variable) -> str:
    _, target = variable.split(SPECIAL_VARIABLE_DELIMITER)
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


def _get_contract_instance(
        contract_container: ContractContainer,
) -> typing.Union[ContractInstance, ChecksumAddress]:
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
    return deployer_account.address


def _validate_transaction_args(
        method: ContractTransactionHandler,
        args: typing.Tuple[Any, ...]
) -> typing.Dict[str, Any]:
    """Validates the transaction arguments against the function ABI."""
    expected_length_abis = [abi for abi in method.abis if len(abi.inputs) == len(args)]
    for abi in expected_length_abis:
        named_args = {}
        for arg, abi_input in zip(args, abi.inputs):
            if not w3.is_encodable(abi_input.type, arg):
                break
            named_args[abi_input.name] = arg
        else:
            return named_args
    raise ValueError(f"Could not find ABI for {method} with {len(args)} args and given types")


def _resolve_contract_address(variable: str) -> str:
    """Resolves a contract address."""
    contract_container = get_contract_container(variable)
    contract_instance = _get_contract_instance(contract_container)
    if contract_instance == ZERO_ADDRESS:
        return ZERO_ADDRESS
    return contract_instance.address


def _resolve_special_variable(variable: str, constants) -> Any:
    if _is_proxy_variable(variable):
        result = _resolve_proxy_address(variable)
    elif _is_deployer(variable):
        result = _resolve_deployer()
    elif _is_constant(variable):
        result = _resolve_constant(variable, constants=constants)
    else:
        raise ValueError(f"Invalid special variable {variable}")
    return result


def _resolve_param(value: Any, constants) -> Any:
    """Resolves a single parameter value or a list of parameter values."""
    if isinstance(value, list):
        return [_resolve_param(v, constants) for v in value]
    if not _is_variable(value):
        return value  # literally a value
    variable = value.strip(VARIABLE_PREFIX)
    if _is_special_variable(variable):
        result = _resolve_special_variable(variable, constants=constants)
    else:
        result = _resolve_contract_address(variable)
    return result


def _resolve_constant(name: str, constants: typing.Dict[str, Any]) -> Any:
    try:
        value = constants[name]
        return value
    except KeyError:
        raise ValueError(f"Constant '{name}' not found in deployment file.")


def _validate_constructor_param(param: Any, contracts: List[str]) -> None:
    """Validates a single constructor parameter or a list of parameters."""
    if isinstance(param, list):
        for p in param:
            _validate_constructor_param(p, contracts)
        return

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


def _validate_constructor_abi_inputs(
        contract_name: str,
        abi_inputs: List[Any],
        parameters: OrderedDict,
        constants: typing.Dict[str, Any]
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
                f"{contract_name} constructor parameter '{name}' at position {position} does not "
                f"match the expected ABI name '{abi_input.name}'."
            )

        # validate value type
        value_to_validate = _resolve_param(value, constants=constants)
        if not w3.is_encodable(abi_input.type, value_to_validate):
            raise ConstructorParameters.Invalid(
                f"Constructor param name '{name}' at position {position} has a value '{value}' "
                f"whose type does not match expected ABI type '{abi_input.type}'"
            )


def validate_constructor_parameters(contracts, constants) -> None:
    """Validates the constructor parameters for all contracts in a single config."""
    print("Validating constructor parameters...")
    available_contracts = list(contracts.keys())
    for contract, parameters in contracts.items():
        if not isinstance(parameters, dict):
            # this can happen if the yml file is malformed
            raise ValueError(f"Malformed constructor parameter config for {contract}.")
        for value in parameters.values():
            _validate_constructor_param(value, available_contracts)

        contract_container = get_contract_container(contract)
        _validate_constructor_abi_inputs(
            contract_name=contract,
            abi_inputs=contract_container.constructor.abi.inputs,
            parameters=parameters,
            constants=constants,
        )


class ConstructorParameters:
    """Represents the constructor parameters for a set of contracts."""

    class Invalid(Exception):
        """Raised when the constructor parameters are invalid"""

    def __init__(self, parameters: OrderedDict, constants: dict = None):
        self.parameters = parameters
        self.constants = constants or {}
        validate_constructor_parameters(parameters, constants)

    @classmethod
    def from_config(cls, config: typing.Dict) -> "ConstructorParameters":
        """Loads the constructor parameters from a JSON file."""
        contracts_config = OrderedDict()
        for contract in config["contracts"]:
            if isinstance(contract, str):
                contract = {contract: OrderedDict()}
            elif isinstance(contract, dict):
                contract = OrderedDict(contract)
            else:
                raise ValueError("Malformed constructor parameters YAML.")
            contracts_config.update(contract)

        return cls(parameters=contracts_config, constants=config.get("constants"))

    def resolve(self, contract_name: str) -> OrderedDict:
        """Resolves the constructor parameters for a single contract."""
        resolved_params = OrderedDict()
        for name, value in self.parameters[contract_name].items():
            resolved_params[name] = _resolve_param(value, constants=self.constants)
        return resolved_params


class Transactor:
    """
    Represents an ape account plus validated/annotated transaction execution.
    """

    def __init__(self, account: typing.Optional[AccountAPI] = None):
        if account is None:
            self._account = get_user_selected_account()
        else:
            self._account = account

    def get_account(self) -> AccountAPI:
        """Returns the transactor account."""
        return self._account

    def transact(self, method: ContractTransactionHandler, *args) -> ReceiptAPI:
        named_args = _validate_transaction_args(method=method, args=args)
        base_message = (
            f"\nTransacting {method.contract.contract_type.name}"
            f"[{method.contract.address[:10]}].{method}"
        )
        if named_args:
            pretty_args = "\n\t".join(f"{k}={v}" for k, v in named_args.items())
            message = f"{base_message} with arguments:\n\t{pretty_args}"
        else:
            message = f"{base_message} with no arguments"
        print(message)
        _continue()

        result = method(*args, sender=self._account)
        return result


class Deployer(Transactor):
    """
    Represents an ape account plus
    deployment parameters for a set of contracts, plus validated/annotated execution.
    """

    __DEPLOYER_ACCOUNT: AccountAPI = None

    def __init__(
            self,
            config: typing.Dict,
            path: Path,
            verify: bool,
            account: typing.Optional[AccountAPI] = None,
    ):
        check_plugins()
        self.path = path
        self.config = config
        self.registry_filepath = validate_config(config=self.config)
        self.constructor_parameters = ConstructorParameters.from_config(self.config)
        super().__init__(account)
        self._set_account(self._account)
        self.verify = verify
        self._confirm_start()

    @classmethod
    def from_yaml(cls, filepath: Path, *args, **kwargs) -> "Deployer":
        config = _load_yaml(filepath)
        return cls(config=config, path=filepath, *args, **kwargs)

    @classmethod
    def get_account(cls) -> AccountAPI:
        """Returns the deployer account."""
        return cls.__DEPLOYER_ACCOUNT

    @classmethod
    def _set_account(cls, deployer: AccountAPI) -> None:
        """Sets the deployer account."""
        cls.__DEPLOYER_ACCOUNT = deployer

    def _get_kwargs(self) -> typing.Dict[str, Any]:
        """Returns the deployment kwargs."""
        return {"publish": self.verify}

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

    @staticmethod
    def proxy(contract: ContractContainer, proxy_contract: ContractInstance) -> ContractInstance:
        print(
            f"\nWrapping {contract.contract_type.name} in "
            f"at {proxy_contract.contract_type.name}:{proxy_contract.address}."
        )
        return contract.at(proxy_contract.address)

    def finalize(self, deployments: List[ContractInstance]) -> None:
        """
        Publishes the deployments to the registry and optionally to block explorers.
        """
        registry_from_ape_deployments(
            deployments=deployments,
            output_filepath=self.registry_filepath,
        )
        if self.verify:
            verify_contracts(contracts=deployments)

    def _confirm_start(self) -> None:
        """Confirms the start of the deployment."""
        print(
            f"Account: {self.get_account().address}",
            f"Config: {self.path}",
            f"Registry: {self.registry_filepath}",
            f"Verify: {self.verify}",
            f"Ecosystem: {networks.provider.network.ecosystem.name}",
            f"Network: {networks.provider.network.name}",
            f"Chain ID: {networks.provider.network.chain_id}",
            f"Gas Price: {networks.provider.gas_price}",
            sep="\n",
        )
        _continue()
