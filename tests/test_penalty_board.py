"""Tests for PenaltyBoard in isolation (period-oriented penalized providers)."""

import ape
import pytest

PERIOD_DURATION = 3600  # 1 hour


@pytest.fixture(scope="module")
def deployer(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def informer(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def other_account(accounts):
    return accounts[2]


def _zero():
    return "0x0000000000000000000000000000000000000000"


@pytest.fixture
def penalty_board(project, deployer, informer, chain):
    """PenaltyBoard with genesis at current chain time and INFORMER_ROLE granted to informer (no compensation)."""
    genesis_time = chain.pending_timestamp
    contract = project.PenaltyBoard.deploy(
        genesis_time,
        PERIOD_DURATION,
        deployer.address,
        _zero(),
        _zero(),
        0,
        _zero(),
        sender=deployer,
    )
    contract.grantRole(contract.INFORMER_ROLE(), informer.address, sender=deployer)
    return contract


def test_constructor_admin_required(project, deployer, chain):
    genesis_time = chain.pending_timestamp
    zero = "0x0000000000000000000000000000000000000000"
    with ape.reverts("Admin required"):
        project.PenaltyBoard.deploy(
            genesis_time,
            PERIOD_DURATION,
            zero,
            zero,
            zero,
            0,
            zero,
            sender=deployer,
        )


def test_only_informer_can_set_penalized_providers(
    penalty_board, deployer, informer, other_account
):
    """Only an account with INFORMER_ROLE can call setPenalizedProvidersForPeriod."""
    current = penalty_board.getCurrentPeriod()
    provs = [other_account.address]

    with ape.reverts():
        penalty_board.setPenalizedProvidersForPeriod(provs, current, sender=deployer)

    penalty_board.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(current) == provs


def test_period_must_be_current_or_previous(
    penalty_board, chain, informer, other_account
):
    """setPenalizedProvidersForPeriod accepts only current or previous period."""
    provs = [other_account.address]

    current = penalty_board.getCurrentPeriod()
    # At deploy, genesis = chain.pending_timestamp so current is 0. Period 1 is invalid.
    with ape.reverts("Invalid period"):
        penalty_board.setPenalizedProvidersForPeriod(provs, current + 1, sender=informer)

    penalty_board.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(current) == provs

    # Advance into period 1; then both 0 and 1 are valid.
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board.getCurrentPeriod() == 1

    penalty_board.setPenalizedProvidersForPeriod(provs, 0, sender=informer)
    penalty_board.setPenalizedProvidersForPeriod(provs, 1, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(0) == provs
    assert penalty_board.getPenalizedProvidersForPeriod(1) == provs

    # Period 2 is invalid (not current or previous).
    with ape.reverts("Invalid period"):
        penalty_board.setPenalizedProvidersForPeriod(provs, 2, sender=informer)


def test_getter_returns_set_list(
    penalty_board, informer, other_account, accounts
):
    """getPenalizedProvidersForPeriod returns the list set for that period."""
    current = penalty_board.getCurrentPeriod()
    provs = [accounts[3].address, accounts[4].address, other_account.address]

    penalty_board.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(current) == provs


def test_setting_again_replaces_list(
    penalty_board, informer, other_account, accounts
):
    """Calling setPenalizedProvidersForPeriod again for the same period replaces the list."""
    current = penalty_board.getCurrentPeriod()

    first = [accounts[5].address, accounts[6].address]
    penalty_board.setPenalizedProvidersForPeriod(first, current, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(current) == first

    second = [other_account.address]
    penalty_board.setPenalizedProvidersForPeriod(second, current, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(current) == second


def test_period_zero_only_when_current_is_zero(
    penalty_board, informer, other_account
):
    """When current period is 0, only period 0 is allowed (no underflow on previous)."""
    current = penalty_board.getCurrentPeriod()
    if current != 0:
        pytest.skip("chain already past period 0")

    provs = [other_account.address]
    penalty_board.setPenalizedProvidersForPeriod(provs, 0, sender=informer)
    assert penalty_board.getPenalizedProvidersForPeriod(0) == provs

    with ape.reverts("Invalid period"):
        penalty_board.setPenalizedProvidersForPeriod(provs, 1, sender=informer)
