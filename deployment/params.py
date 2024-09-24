import typing
from abc import ABC, abstractmethod
from collections import OrderedDict, namedtuple
from pathlib import Path
from typing import Any, List

from ape import chain, networks, project
from ape.api import AccountAPI, ReceiptAPI
from ape.cli.choices import select_account
from ape.contracts.base import ContractContainer, ContractInstance, ContractTransactionHandler
from ape.utils import EMPTY_BYTES32, ZERO_ADDRESS
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from ethpm_types import MethodABI
from web3.auto import w3

from deployment.confirm import _confirm_resolution, _continue
from deployment.constants import EIP1967_ADMIN_SLOT, OZ_DEPENDENCY
from deployment.registry import registry_from_ape_deployments
from deployment.utils import (
    _load_yaml,
    check_plugins,
    get_contract_container,
    validate_config,
    verify_contracts,
)

CONTRACT_CONSTRUCTOR_PARAMETER_KEY = "constructor"
CONTRACT_PROXY_PARAMETER_KEY = "proxy"


class VariableContext:
    def __init__(
        self,
        contract_names: List[str],
        contract_name: str,
        constants: typing.Dict[str, Any] = None,
        check_for_proxy_instances: bool = True,
    ):
        self.contract_names = contract_names or list()
        self.contract_name = contract_name
        self.constants = constants or dict()
        self.check_for_proxy_instances = check_for_proxy_instances


# Variables


class Variable(ABC):
    VARIABLE_PREFIX = "$"

    @abstractmethod
    def resolve(self) -> Any:
        raise NotImplementedError

    @classmethod
    def is_variable(cls, param: Any) -> bool:
        """Returns True if the param is a variable."""
        result = isinstance(param, str) and param.startswith(cls.VARIABLE_PREFIX)
        return result


class DeployerAccount(Variable):
    DEPLOYER_INDICATOR = "deployer"

    @classmethod
    def is_deployer(cls, value: str) -> bool:
        """Returns True if the variable is a special deployer variable."""
        return value == cls.DEPLOYER_INDICATOR

    def resolve(self) -> Any:
        deployer_account = Deployer.get_account()
        if deployer_account is None:
            return ZERO_ADDRESS
        return deployer_account.address


class Constant(Variable):  # oxymoron anyone (except David :P)...
    def __init__(self, constant_name: str, context: VariableContext):
        try:
            self.constant_value = context.constants[constant_name]
        except KeyError:
            raise ValueError(f"Constant '{constant_name}' not found in deployment file.")

    @classmethod
    def is_constant(cls, value: str) -> bool:
        """Returns True if the variable is a deployment constant."""
        return value.isupper()

    def resolve(self) -> Any:
        return self.constant_value


class Encode(Variable):
    ENCODE_PREFIX = "encode:"

    def __init__(self, variable: str, context: VariableContext):
        variable = variable[len(self.ENCODE_PREFIX) :]
        self.method_name, self.method_args = self._get_call_data(variable, context)
        self.contract_name = context.contract_name

    @staticmethod
    def _get_call_data(variable, context) -> typing.Tuple[str, List[Any]]:
        variable_elements = variable.split(",")
        method_name = variable_elements[0]
        method_args = [_process_raw_value(arg, context) for arg in variable_elements[1:]]

        contract_name = context.contract_name
        contract_container = get_contract_container(contract_name)
        contract_method_abis = contract_container.contract_type.methods
        specific_method_abis = [abi for abi in contract_method_abis if abi.name == method_name]

        resolved_method_args = [_resolve_param(method_arg) for method_arg in method_args]
        _validate_method_args(method_abis=specific_method_abis, args=resolved_method_args)

        return method_name, method_args

    @classmethod
    def is_encode(cls, value: str) -> bool:
        """Returns True if the variable is a variable that needs encoding to bytes"""
        return value.startswith(cls.ENCODE_PREFIX)

    def resolve(self) -> Any:
        contract_container = get_contract_container(self.contract_name)
        contract_instance = _get_contract_instance(contract_container)
        if contract_instance == ZERO_ADDRESS:
            # logic contract not yet deployed - in eager validation check
            return "0xdeadbeef"  # something noticeable in case ever actually returned

        resolved_method_args = [_resolve_param(method_arg) for method_arg in self.method_args]

        method_handler = getattr(contract_instance, self.method_name)
        encoded_bytes = method_handler.encode_input(*resolved_method_args)
        return encoded_bytes.hex()  # return as hex - just cleaner


class ContractName(Variable):
    def __init__(self, contract_name: str, context: VariableContext):
        if contract_name not in context.contract_names:
            raise ValueError(f"Contract name {contract_name} not found")

        self.contract_name = contract_name
        self.check_for_proxy_instances = context.check_for_proxy_instances

    def resolve(self) -> Any:
        """Resolves a contract address."""
        contract_container = get_contract_container(self.contract_name)
        contract_instance = _get_contract_instance(contract_container)
        if contract_instance == ZERO_ADDRESS:
            # eager validation
            return ZERO_ADDRESS

        if self.check_for_proxy_instances:
            # check if contract is proxied - if so return proxy contract instead
            local_proxies = chain.contracts._local_proxies
            for proxy_address, proxy_info in local_proxies.items():
                if proxy_info.target == contract_instance.address:
                    return proxy_address

        return contract_instance.address


def _get_contract_instance(
    contract_container: ContractContainer,
) -> typing.Union[ContractInstance, ChecksumAddress]:
    contract_instances = contract_container.deployments
    if not contract_instances:
        return ZERO_ADDRESS
    if len(contract_instances) != 1:
        raise ValueError(
            f"Variable {contract_container.contract_type.name} is ambiguous - "
            f"expected exactly one contract instance, got {len(contract_instances)}"
            " Checkout ~/.ape/<NETWORK>/deployments_map.json"
        )
    contract_instance = contract_instances[0]
    return contract_instance


def _resolve_param(value: Any) -> Any:
    """Resolves a single parameter value or a list of parameter values."""
    if isinstance(value, list):
        return [_resolve_param(v) for v in value]

    if isinstance(value, Variable):
        return value.resolve()

    return value  # literally a value


def _resolve_params(parameters: OrderedDict) -> OrderedDict:
    resolved_parameters = OrderedDict()
    for name, value in parameters.items():
        resolved_parameters[name] = _resolve_param(value)

    return resolved_parameters


def _variable_from_value(variable: Any, context: VariableContext) -> Variable:
    variable = variable.strip(Variable.VARIABLE_PREFIX)
    if DeployerAccount.is_deployer(variable):
        return DeployerAccount()
    elif Encode.is_encode(variable):
        return Encode(variable, context)
    elif Constant.is_constant(variable):
        return Constant(variable, context)
    else:
        return ContractName(variable, context)


def _process_raw_value(value: Any, variable_context: VariableContext) -> Any:
    if isinstance(value, list):
        return [_process_raw_value(v, variable_context) for v in value]

    if Variable.is_variable(value):
        value = _variable_from_value(value, variable_context)

    return value


def _process_raw_values(values: OrderedDict, variable_context: VariableContext) -> OrderedDict:
    processed_parameters = OrderedDict()
    for name, value in values.items():
        processed_parameters[name] = _process_raw_value(value, variable_context)

    return processed_parameters


def _get_contract_names(config: typing.Dict) -> List[str]:
    contract_names = list()
    for contract_info in config["contracts"]:
        if isinstance(contract_info, str):
            contract_names.append(contract_info)
        elif isinstance(contract_info, dict):
            contract_names.extend(list(contract_info.keys()))
        else:
            raise ValueError("Malformed constructor parameters YAML.")

    return contract_names


def _validate_method_args(
    method_abis: List[MethodABI], args: typing.Sequence[Any]
) -> typing.Dict[str, Any]:
    """Validates the transaction arguments against the function ABI."""
    if len(method_abis) == 0:
        raise ValueError("No method abis provided for validation of args")

    abis_matching_args_length = [abi for abi in method_abis if len(abi.inputs) == len(args)]
    for abi in abis_matching_args_length:
        named_args = {}
        for arg, abi_input in zip(args, abi.inputs):
            if not w3.is_encodable(abi_input.type, arg):
                break
            named_args[abi_input.name] = arg
        else:
            return named_args
    raise ValueError(
        f"Could not find ABI for '{method_abis[0].name}' with {len(args)} arg(s) and given type(s)"
    )


def _validate_constructor_abi_inputs(
    contract_name: str,
    abi_inputs: List[Any],
    resolved_parameters: OrderedDict,
) -> None:
    """Validates the constructor parameters against the constructor ABI."""
    if len(resolved_parameters) != len(abi_inputs):
        raise ConstructorParameters.Invalid(
            f"Constructor parameters length mismatch - "
            f"{contract_name} ABI requires {len(abi_inputs)}, Got {len(resolved_parameters)}."
        )
    if not abi_inputs:
        return  # no constructor parameters

    codex = enumerate(zip(abi_inputs, resolved_parameters.items()), start=0)
    for position, (abi_input, resolved_input) in codex:
        name, value = resolved_input
        # validate name
        if abi_input.name != name:
            raise ConstructorParameters.Invalid(
                f"{contract_name} constructor parameter '{name}' at position {position} does not "
                f"match the expected ABI name '{abi_input.name}'."
            )

        # validate value type
        if not w3.is_encodable(abi_input.type, value):
            raise ConstructorParameters.Invalid(
                f"Constructor param name '{name}' at position {position} has a value '{value}' "
                f"whose type does not match expected ABI type '{abi_input.type}'"
            )


def validate_constructor_parameters(contracts_parameters) -> None:
    """Validates the constructor parameters for all contracts in a single config."""
    for contract, parameters in contracts_parameters.items():
        if not isinstance(parameters, dict):
            # this can happen if the yml file is malformed
            raise ValueError(f"Malformed constructor parameter config for {contract}.")

        resolved_parameters = _resolve_params(parameters=parameters)
        contract_container = get_contract_container(contract)
        _validate_constructor_abi_inputs(
            contract_name=contract,
            abi_inputs=contract_container.constructor.abi.inputs,
            resolved_parameters=resolved_parameters,
        )


class ConstructorParameters:
    """Represents the constructor parameters for a set of contracts."""

    class Invalid(Exception):
        """Raised when the constructor parameters are invalid"""

    def __init__(self, parameters: OrderedDict):
        self.parameters = parameters
        validate_constructor_parameters(parameters)

    @classmethod
    def from_config(cls, config: typing.Dict) -> "ConstructorParameters":
        """Loads the constructor parameters from a JSON file."""
        print("Processing contract constructor parameters...")
        contracts_config = OrderedDict()
        contract_names = _get_contract_names(config)
        constants = config.get("constants")
        for contract_info in config["contracts"]:
            if isinstance(contract_info, str):
                contract_constructor_params = {contract_info: OrderedDict()}
            elif isinstance(contract_info, dict):
                if len(contract_info) != 1:
                    raise ValueError("Malformed constructor parameters YAML.")

                contract_name = list(contract_info.keys())[0]  # only one entry
                contract_data = contract_info[contract_name]
                parameter_values = cls._process_parameters(
                    constants, contract_data, contract_name, contract_names
                )

                contract_constructor_params = {contract_name: parameter_values}
            else:
                raise ValueError("Malformed constructor parameters YAML.")
            contracts_config.update(contract_constructor_params)

        return cls(parameters=contracts_config)

    @classmethod
    def _process_parameters(cls, constants, contract_data, contract_name, contract_names):
        parameter_values = OrderedDict()
        if CONTRACT_CONSTRUCTOR_PARAMETER_KEY in contract_data:
            parameter_values = _process_raw_values(
                contract_data[CONTRACT_CONSTRUCTOR_PARAMETER_KEY],
                VariableContext(
                    contract_names=contract_names, constants=constants, contract_name=contract_name
                ),
            )
        return parameter_values

    def resolve(self, contract_name: str) -> OrderedDict:
        """Resolves the constructor parameters for a single contract."""
        resolved_params = _resolve_params(self.parameters[contract_name])
        return resolved_params


def validate_proxy_info(contracts_proxy_info) -> None:
    """Validates the proxy information for all contracts."""
    contract_container = OZ_DEPENDENCY.TransparentUpgradeableProxy
    for contract, proxy_info in contracts_proxy_info.items():
        resolved_parameters = _resolve_params(proxy_info.constructor_params)
        _validate_constructor_abi_inputs(
            contract_name=contract_container.contract_type.name,
            abi_inputs=contract_container.constructor.abi.inputs,
            resolved_parameters=resolved_parameters,
        )


class ProxyParameters:
    """Represents the proxy parameters for contracts that are to be proxied"""

    CONTRACT_TYPE = "contract_type"
    PROXY_NAME = "TransparentUpgradeableProxy"

    class Invalid(Exception):
        """Raised when the constructor parameters are invalid"""

    class ProxyInfo(typing.NamedTuple):
        contract_type_container: ContractContainer
        constructor_params: OrderedDict

    def __init__(self, contracts_proxy_info: OrderedDict):
        self.contracts_proxy_info = contracts_proxy_info
        validate_proxy_info(contracts_proxy_info)

    @classmethod
    def from_config(cls, config: typing.Dict) -> "ProxyParameters":
        """Loads the proxy parameters from a JSON config file."""
        print("Processing proxy parameters...")
        contract_names = _get_contract_names(config)
        constants = config.get("constants")

        contracts_proxy_info = OrderedDict()
        for contract_info in config["contracts"]:
            if isinstance(contract_info, str):
                continue

            if not isinstance(contract_info, dict) or len(contract_info) != 1:
                raise ValueError("Malformed constructor parameters YAML.")

            contract_name = list(contract_info.keys())[0]  # only one entry
            contract_data = contract_info[contract_name]
            if CONTRACT_PROXY_PARAMETER_KEY not in contract_data:
                continue

            proxy_info = cls._generate_proxy_info(
                contract_data,
                VariableContext(
                    contract_names=contract_names,
                    constants=constants,
                    contract_name=contract_name,
                    check_for_proxy_instances=False,
                ),
            )
            contracts_proxy_info.update({contract_name: proxy_info})

        return cls(contracts_proxy_info=contracts_proxy_info)

    def contract_needs_proxy(self, contract_name) -> bool:
        proxy_info = self.contracts_proxy_info.get(contract_name)
        return proxy_info is not None

    def resolve(self, contract_name: str) -> typing.Tuple[ContractContainer, OrderedDict]:
        """
        Resolves the proxy data for a single contract.
        """
        proxy_info = self.contracts_proxy_info.get(contract_name)
        if not proxy_info:
            raise ValueError(f"Unexpected contract to proxy: {contract_name}")

        contract_container = proxy_info.contract_type_container

        resolved_params = _resolve_params(parameters=proxy_info.constructor_params)
        return contract_container, resolved_params

    @classmethod
    def _generate_proxy_info(cls, contract_data, variable_context: VariableContext) -> ProxyInfo:
        proxy_data = contract_data[CONTRACT_PROXY_PARAMETER_KEY] or dict()

        contract_type = variable_context.contract_name
        if cls.CONTRACT_TYPE in proxy_data:
            contract_type = proxy_data[cls.CONTRACT_TYPE]
        contract_type_container = get_contract_container(contract_type)

        constructor_data = cls._default_proxy_parameters(variable_context.contract_name)
        if CONTRACT_CONSTRUCTOR_PARAMETER_KEY in proxy_data:
            proxy_constructor_params = proxy_data[CONTRACT_CONSTRUCTOR_PARAMETER_KEY]
            if "_logic" in proxy_constructor_params:
                raise cls.Invalid(
                    "'_logic' parameter cannot be specified: it is implicitly "
                    "the contract being proxied"
                )

            constructor_data.update(proxy_constructor_params)

        processed_values = _process_raw_values(constructor_data, variable_context)
        proxy_info = cls.ProxyInfo(
            contract_type_container=contract_type_container, constructor_params=processed_values
        )
        return proxy_info

    @classmethod
    def _default_proxy_parameters(cls, contract_name: str) -> OrderedDict:
        default_parameters = OrderedDict(
            {"_logic": f"${contract_name}", "initialOwner": "$deployer", "_data": b""}
        )
        return default_parameters


class Transactor:
    """
    Represents an ape account plus validated/annotated transaction execution.
    """

    def __init__(self, account: typing.Optional[AccountAPI] = None, autosign: bool = False):
        if account is None:
            self._account = select_account()
        else:
            self._account = account
        if autosign:
            print("WARNING: Autosign is enabled. Transactions will be signed automatically.")
        self._autosign = autosign
        self._account.set_autosign(autosign)

    def get_account(self) -> AccountAPI:
        """Returns the transactor account."""
        return self._account

    def transact(self, method: ContractTransactionHandler, *args) -> ReceiptAPI:
        named_args = _validate_method_args(method_abis=method.abis, args=args)
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
        if not self._autosign:
            _continue()

        result = method(
            *args,
            sender=self._account,
            # FIXME: Manual gas fees - #199
            # max_priority_fee="3 gwei",
            # max_fee="120 gwei"
        )
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
        autosign: bool = False,
    ):
        super().__init__(account, autosign)

        check_plugins()
        self.path = path
        self.config = config
        self.registry_filepath = validate_config(config=self.config)
        self.constructor_parameters = ConstructorParameters.from_config(self.config)
        self.proxy_parameters = ProxyParameters.from_config(self.config)

        # Little trick to expose contracts as attributes (e.g., deployer.constants.FOO)
        constants = config.get("constants", {})
        _Constants = namedtuple("_Constants", list(constants))
        self.constants = _Constants(**constants)

        self._set_account(self._account)
        self.verify = verify
        self._print_deployment_info()

        if not self._autosign:
            # Confirms the start of the deployment.
            _continue()

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

    def deploy(self, container: ContractContainer) -> ContractInstance:
        contract_name = container.contract_type.name

        resolved_constructor_params = self.constructor_parameters.resolve(contract_name)
        instance = self._deploy_contract(container, resolved_constructor_params)

        if self.proxy_parameters.contract_needs_proxy(contract_name):
            contract_type_container, resolved_proxy_params = self.proxy_parameters.resolve(
                contract_name=contract_name
            )
            instance = self._deploy_proxy(
                contract_name, contract_type_container, resolved_proxy_params
            )

        return instance

    def _deploy_contract(
        self, container: ContractContainer, resolved_params: OrderedDict
    ) -> ContractInstance:
        contract_name = container.contract_type.name
        if not self._autosign:
            _confirm_resolution(resolved_params, contract_name)
        deployment_params = [container, *resolved_params.values()]
        kwargs = self._get_kwargs()

        deployer_account = self.get_account()
        return deployer_account.deploy(
            *deployment_params,
            # FIXME: Manual gas fees - #199
            #    max_priority_fee="3 gwei",
            #    max_fee="120 gwei",
            **kwargs,
        )

    def _deploy_proxy(
        self,
        target_contract_name: str,
        contract_type_container: ContractContainer,
        resolved_proxy_params: OrderedDict,
    ) -> ContractInstance:
        proxy_container = OZ_DEPENDENCY.TransparentUpgradeableProxy
        print(
            f"\nDeploying {proxy_container.contract_type.name} "
            f"contract to proxy {target_contract_name}."
        )
        proxy_contract = self._deploy_contract(
            proxy_container, resolved_params=resolved_proxy_params
        )
        print(
            f"\nWrapping {target_contract_name} into {proxy_contract.contract_type.name} "
            f"(as type {contract_type_container.contract_type.name}) "
            f"at {proxy_contract.address}."
        )
        return contract_type_container.at(proxy_contract.address)

    def upgrade(self, container: ContractContainer, proxy_address, data=b"") -> ContractInstance:
        implementation = self.deploy(container)
        # upgrade proxy to implementation
        return self.upgradeTo(implementation, proxy_address, data)

    def upgradeTo(
        self, implementation: ContractInstance, proxy_address, data=b""
    ) -> ContractInstance:
        admin_slot = chain.provider.get_storage_at(address=proxy_address, slot=EIP1967_ADMIN_SLOT)

        if admin_slot == EMPTY_BYTES32:
            raise ValueError(
                f"Admin slot for contract at {proxy_address} is empty. "
                "Are you sure this is an EIP1967-compatible proxy?"
            )

        admin_address = to_checksum_address(admin_slot[-20:])
        proxy_admin = OZ_DEPENDENCY.ProxyAdmin.at(admin_address)
        # TODO: Check that owner of proxy admin is deployer

        self.transact(proxy_admin.upgradeAndCall, proxy_address, implementation.address, data)

        wrapped_instance = getattr(project, implementation.contract_type.name).at(proxy_address)
        return wrapped_instance

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

    def _print_deployment_info(self):
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
