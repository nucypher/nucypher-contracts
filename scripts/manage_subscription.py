import click
from ape import Contract
from ape.cli import account_option, ConnectedProviderCommand

from deployment import registry
from deployment.options import (
    subscription_contract_option,
    domain_option,
    access_controller_option,
    ritual_id_option,
    encryptor_slots_option,
    encryptors_option,
)
from deployment.params import Transactor
from deployment.utils import check_plugins


def _erc20_approve(
        amount: int,
        erc20: Contract,
        receiver: Contract,
        transactor: Transactor
) -> None:
    """Approve an ERC20 transfer."""
    click.echo(
        f"Approving transfer of {amount} {erc20.contract_type.name} "
        f"to {receiver.contract_type.name}."
    )
    transactor.transact(
        erc20.approve,
        receiver.address,
        amount
    )


def _calculate_slot_fees(
        subscription_contract: Contract,
        slots: int
) -> int:
    """Calculate the fees for a given number of encryptor slots."""
    duration = subscription_contract.subscriptionPeriodDuration()
    encryptor_fees = subscription_contract.encryptorFees(slots, duration)
    total_fees = encryptor_fees
    return total_fees


@click.group()
def cli():
    """Subscription Management CLI"""


@cli.command(cls=ConnectedProviderCommand)
@account_option()
@domain_option
@subscription_contract_option
@encryptor_slots_option
@click.option(
    "--period",
    default=0,
    help="Subscription billing period number to pay for.",
)
def pay_subscription(account, domain, subscription_contract, encryptor_slots, period):
    """Pay for a new subscription period and initial encryptor slots."""
    check_plugins()
    transactor = Transactor(account=account)
    subscription_contract = registry.get_contract(
        contract_name=subscription_contract,
        domain=domain
    )
    erc20 = Contract(subscription_contract.feeToken())
    base_fees = subscription_contract.baseFees(period)
    slot_fees = _calculate_slot_fees(
        subscription_contract=subscription_contract,
        slots=encryptor_slots
    )
    total_fees = base_fees + slot_fees
    _erc20_approve(
        amount=total_fees,
        erc20=erc20,
        receiver=subscription_contract,
        transactor=transactor
    )
    click.echo(
        f"Paying for subscription period #{period} "
        f"with {encryptor_slots} encryptor slots."
    )
    transactor.transact(
        subscription_contract.payForSubscription,
        encryptor_slots
    )


@cli.command(cls=ConnectedProviderCommand)
@account_option()
@domain_option
@subscription_contract_option
@encryptor_slots_option
def pay_slots(account, domain, subscription_contract, encryptor_slots):
    """Pay for additional encryptor slots in the current billing period."""
    check_plugins()
    transactor = Transactor(account=account)
    subscription_contract = registry.get_contract(
        contract_name=subscription_contract,
        domain=domain
    )
    erc20 = Contract(subscription_contract.feeToken())
    fee = _calculate_slot_fees(
        subscription_contract=subscription_contract,
        slots=encryptor_slots
    )
    _erc20_approve(
        amount=fee,
        erc20=erc20,
        receiver=subscription_contract,
        transactor=transactor
    )
    click.echo(f"Paying for {encryptor_slots} new encryptor slots.")
    transactor.transact(
        subscription_contract.payForEncryptorSlots,
        encryptor_slots
    )


@cli.command(cls=ConnectedProviderCommand)
@account_option()
@domain_option
@ritual_id_option
@access_controller_option
@encryptors_option
def add_encryptors(account, domain, ritual_id, access_controller, encryptors):
    """Authorize encryptors to the access control contract for a ritual."""
    access_controller = registry.get_contract(
        contract_name=access_controller,
        domain=domain
    )
    transactor = Transactor(account=account)
    click.echo(
        f"Adding {len(encryptors)} encryptors "
        f"to the {access_controller} "
        f"for ritual {ritual_id}."
    )
    transactor.transact(
        access_controller.authorize,
        ritual_id,
        encryptors
    )


@cli.command(cls=ConnectedProviderCommand)
@account_option()
@domain_option
@ritual_id_option
@access_controller_option
@encryptors_option
def remove_encryptors(account, domain, ritual_id, access_controller, encryptors):
    """Deauthorize encryptors from the access control contract for a ritual."""
    transactor = Transactor(account=account)
    access_controller = registry.get_contract(
        contract_name=access_controller,
        domain=domain
    )
    click.echo(
        f"Removing {len(encryptors)} "
        f"encryptors to the {access_controller} "
        f"for ritual {ritual_id}."
    )
    transactor.transact(
        access_controller.authorize,
        ritual_id, encryptors
    )


if __name__ == "__main__":
    cli()
