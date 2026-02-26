"""TDD tests for PenaltyBoard compensation. Some pass with stubs; others fail until C3 implementation."""

import ape
import pytest

PERIOD_DURATION = 3600
FIXED_COMPENSATION = 1000
TOKEN_SUPPLY = 1_000_000 * 10**18


@pytest.fixture(scope="module")
def deployer(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def informer(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def fund_holder(accounts):
    return accounts[2]


@pytest.fixture(scope="module")
def staking_provider(accounts):
    return accounts[3]


@pytest.fixture(scope="module")
def beneficiary(accounts):
    return accounts[4]


@pytest.fixture(scope="module")
def other_account(accounts):
    return accounts[5]


@pytest.fixture(scope="module")
def mock_taco(project, deployer):
    return project.MockTACoForPenaltyBoard.deploy(sender=deployer)


@pytest.fixture(scope="module")
def token(project, deployer):
    return project.TestToken.deploy(TOKEN_SUPPLY, sender=deployer)


@pytest.fixture
def penalty_board_comp(project, deployer, informer, chain, mock_taco, token, fund_holder):
    """PenaltyBoard with compensation enabled (7-arg constructor)."""
    genesis_time = chain.pending_timestamp
    contract = project.PenaltyBoard.deploy(
        genesis_time,
        PERIOD_DURATION,
        deployer.address,
        mock_taco.address,
        token.address,
        FIXED_COMPENSATION,
        fund_holder.address,
        sender=deployer,
    )
    contract.grantRole(contract.INFORMER_ROLE(), informer.address, sender=deployer)
    return contract


@pytest.fixture
def registered_staker(mock_taco, staking_provider, deployer, beneficiary):
    """Register staking_provider in mock TACo: owner=deployer, beneficiary=beneficiary, not stakeless."""
    mock_taco.setRoles(
        staking_provider.address,
        deployer.address,
        beneficiary.address,
        False,
        sender=deployer,
    )


def test_penalized_periods_by_staker_updated(
    penalty_board_comp, informer, staking_provider
):
    """setPenalizedProvidersForPeriod(provs, period) causes penalizedPeriodsByStaker[prov] to include period."""
    current = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    penalty_board_comp.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [current]


def test_penalized_periods_monotonic_append(
    penalty_board_comp, informer, staking_provider, chain
):
    """Calling setPenalizedProvidersForPeriod for different periods appends to each staker's list (monotonic)."""
    current = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    penalty_board_comp.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == current + 1
    penalty_board_comp.setPenalizedProvidersForPeriod(provs, current + 1, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [
        current,
        current + 1,
    ]


def test_withdraw_reverts_until_implemented(
    penalty_board_comp, registered_staker, beneficiary, staking_provider
):
    """Withdraw reverts with 'Not implemented' until C3 (stub)."""
    with ape.reverts("Not implemented"):
        penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)


def test_get_accrued_balance_zero_without_accrual(penalty_board_comp, staking_provider):
    """getAccruedBalance returns 0 before accrual is implemented (stub)."""
    assert penalty_board_comp.getAccruedBalance(staking_provider.address) == 0


def test_accrual_with_no_penalties_gives_positive_balance(
    penalty_board_comp, chain, staking_provider, registered_staker
):
    """After advancing periods with no penalties, staker should have positive accrued balance (fails until C3)."""
    # Advance 2 periods so there is something to accrue
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance > 0, "Accrual not implemented: getAccruedBalance should be > 0 after 2 periods with no penalties"


def test_only_owner_provider_beneficiary_can_withdraw(
    penalty_board_comp, registered_staker, other_account, staking_provider
):
    """Only owner, staking provider, or beneficiary may call withdraw; others revert (C3: Unauthorized; stub: Not implemented)."""
    with ape.reverts():
        penalty_board_comp.withdraw(staking_provider.address, sender=other_account)


def test_withdraw_sends_tokens_to_beneficiary(
    penalty_board_comp,
    token,
    fund_holder,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    deployer,
):
    """Withdraw sends tokens to beneficiary, not to msg.sender (fails until C3 implements transfer)."""
    # Fund the fundHolder and approve PenaltyBoard (token was minted to deployer)
    token.transfer(fund_holder.address, FIXED_COMPENSATION * 10, sender=deployer)
    token.approve(
        penalty_board_comp.address,
        2**256 - 1,
        sender=fund_holder,
    )
    # Advance so there is accrual (when implemented)
    chain.pending_timestamp += PERIOD_DURATION
    before = token.balanceOf(beneficiary.address)
    # Beneficiary calls withdraw for staking_provider
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after > before, "Withdraw should send tokens to beneficiary"


def test_stakeless_staker_gets_zero_compensation(
    penalty_board_comp, mock_taco, chain, deployer, beneficiary, accounts
):
    """Stakeless staker accrues 0 (fails until C3 implements stakeless check)."""
    stakeless_provider = accounts[6]
    mock_taco.setRoles(
        stakeless_provider.address,
        deployer.address,
        beneficiary.address,
        True,  # stakeless
        sender=deployer,
    )
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(stakeless_provider.address)
    assert balance == 0, "Stakeless staker should have 0 accrued compensation"
