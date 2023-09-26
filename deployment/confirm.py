from collections import OrderedDict

from deployment.constants import NULL_ADDRESS


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
