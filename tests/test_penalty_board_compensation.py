"""TDD tests for PenaltyBoard compensation. Some pass with stubs; others fail until C3 implementation."""

import ape
import pytest

PERIOD_DURATION = 3600
FULL_COMPENSATION = 1000
REDUCED_COMPENSATION_1 = 600
REDUCED_COMPENSATION_2 = 100
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
def mock_taco_app(project, deployer):
    return project.MockTACoForPenaltyBoard.deploy(sender=deployer)


@pytest.fixture(scope="module")
def token(project, deployer):
    return project.TestToken.deploy(TOKEN_SUPPLY, sender=deployer)


@pytest.fixture
def penalty_board_comp(project, deployer, informer, chain, mock_taco_app, token, fund_holder):
    """PenaltyBoard with compensation enabled (7-arg constructor)."""
    genesis_time = chain.pending_timestamp
    contract = project.PenaltyBoard.deploy(
        genesis_time,
        PERIOD_DURATION,
        deployer.address,
        mock_taco_app.address,
        token.address,
        FULL_COMPENSATION,
        REDUCED_COMPENSATION_1,
        REDUCED_COMPENSATION_2,
        fund_holder.address,
        sender=deployer,
    )
    contract.grantRole(contract.INFORMER_ROLE(), informer.address, sender=deployer)
    token.transfer(fund_holder.address, 100 * FULL_COMPENSATION, sender=deployer)
    token.approve(contract.address, 2**256 - 1, sender=fund_holder)
    return contract


@pytest.fixture
def registered_staker(mock_taco_app, staking_provider, deployer, beneficiary):
    """Register staking_provider in mock TACo: owner=deployer, beneficiary=beneficiary, not stakeless."""
    mock_taco_app.setRoles(
        staking_provider.address,
        deployer.address,
        beneficiary.address,
        False,
        sender=deployer,
    )


def test_penalized_periods_by_staker_updated(penalty_board_comp, informer, staking_provider):
    """setPenalizedProvidersForPeriod(provs, period) causes penalizedPeriodsByStaker[prov] to include period."""
    current = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    penalty_board_comp.setPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [current]


def test_penalized_periods_monotonic_append(penalty_board_comp, informer, staking_provider, chain):
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


def test_withdraw_reverts_nothing_to_withdraw_for_stakeless(
    penalty_board_comp, mock_taco_app, deployer, beneficiary, accounts, chain
):
    """Withdraw reverts with 'Nothing to withdraw' for stakeless staker (no accrual)."""
    stakeless_provider = accounts[6]
    mock_taco_app.setRoles(
        stakeless_provider.address,
        deployer.address,
        beneficiary.address,
        True,  # stakeless
        sender=deployer,
    )
    chain.pending_timestamp += 2 * PERIOD_DURATION
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(stakeless_provider.address, sender=beneficiary)


def test_get_accrued_balance_reflects_periods_without_prior_withdraw(
    penalty_board_comp, staking_provider, registered_staker, chain
):
    """getAccruedBalance returns accrued amount for periods 0..current when staker has not yet withdrawn."""
    # At deploy we are in period 0; one period accrues (fixed per period).
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == FULL_COMPENSATION


def test_accrual_with_no_penalties_gives_positive_balance(
    penalty_board_comp, chain, staking_provider, registered_staker
):
    """After advancing periods with no penalties, staker should have positive accrued balance (fails until C3)."""
    # Advance 2 periods so there is something to accrue
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert (
        balance > 0
    ), "Accrual not implemented: getAccruedBalance should be > 0 after 2 periods with no penalties"


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
    # Advance so there is accrual (when implemented)
    chain.pending_timestamp += 3 * PERIOD_DURATION
    before = token.balanceOf(beneficiary.address)
    # Beneficiary calls withdraw for staking_provider
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after > before, "Withdraw should send tokens to beneficiary"


def test_stakeless_staker_gets_zero_compensation(
    penalty_board_comp, mock_taco_app, chain, deployer, beneficiary, accounts
):
    """Stakeless staker accrues 0 (fails until C3 implements stakeless check)."""
    stakeless_provider = accounts[6]
    mock_taco_app.setRoles(
        stakeless_provider.address,
        deployer.address,
        beneficiary.address,
        True,  # stakeless
        sender=deployer,
    )
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(stakeless_provider.address)
    assert balance == 0, "Stakeless staker should have 0 accrued compensation"


# --- C4: Edge cases ---


def test_first_withdrawal_accrues_from_period_zero(
    penalty_board_comp,
    token,
    fund_holder,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    deployer,
):
    """First withdrawal (sentinel: never accrued) accrues from period 0 to current; full amount to beneficiary."""
    num_periods = 4
    chain.pending_timestamp += (num_periods + 2) * PERIOD_DURATION
    # Periods 0..4 → 5 periods
    expected = (num_periods + 1) * FULL_COMPENSATION

    before = token.balanceOf(beneficiary.address)
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after - before == expected


def test_withdraw_reverts_when_nothing_left_after_prior_withdraw(
    penalty_board_comp,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
):
    """After a full withdraw, second withdraw without time advance reverts with Nothing to withdraw."""
    chain.pending_timestamp += 2 * PERIOD_DURATION
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)


def test_many_periods_full_accrual(
    penalty_board_comp,
    token,
    fund_holder,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    deployer,
):
    """Many periods with no penalties: full accrual (numPeriods * fixed per period)."""
    n = 10
    chain.pending_timestamp += (n + 2) * PERIOD_DURATION
    # Periods 0..n → n+1 periods
    expected = (n + 1) * FULL_COMPENSATION
    before = token.balanceOf(beneficiary.address)
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after - before == expected


@pytest.mark.parametrize(
    "periods",
    [
        # T F F F F T -> 0 1 2 3 4 3 -> F F R1 R2 0 R2
        {
            "penalized_providers": [1, 2, 3, 4],
            "expected": [2, 1, 2],
            "num_periods": 5,
            "intermediate_withdraws": [],
        },
        # F T T T F T -> 1 1 1 1 1 1 -> F F F F F F
        {
            "penalized_providers": [0, 4],
            "expected": [6, 0, 0],
            "num_periods": 5,
            "intermediate_withdraws": [2, 3, 4],
        },
        # T T T F F F T -> 0 0 0 1 2 3 3 -> F F F F R1 R2 R2
        {
            "penalized_providers": [3, 4, 5],
            "expected": [4, 1, 2],
            "num_periods": 6,
            "intermediate_withdraws": [2, 3, 4, 5],
        },
    ],
)
def test_penalty_in_range_reduces_compensation(
    penalty_board_comp,
    token,
    fund_holder,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    deployer,
    informer,
    periods,
):
    """A penalty in period k affects k..k+PENALTY_WINDOW_PERIODS; only unaffected periods get full compensation."""
    penalized_providers = periods["penalized_providers"]
    expected = periods["expected"]
    num_periods = periods["num_periods"]
    intermediate_withdraws = periods["intermediate_withdraws"]

    before = token.balanceOf(beneficiary.address)

    penalty_index = 0
    withdraw_index = 0
    accrued_balance = 0
    for current_period in range(num_periods):
        if (
            withdraw_index < len(intermediate_withdraws)
            and intermediate_withdraws[withdraw_index] == current_period
        ):
            accrued_balance += penalty_board_comp.getAccruedBalance(staking_provider.address)
            penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
            withdraw_index += 1
        if (
            penalty_index < len(penalized_providers)
            and penalized_providers[penalty_index] == current_period
        ):
            penalty_board_comp.setPenalizedProvidersForPeriod(
                [staking_provider.address], current_period, sender=informer
            )
            penalty_index += 1

        chain.pending_timestamp += PERIOD_DURATION

    chain.pending_timestamp += 2 * PERIOD_DURATION

    expected_compensation = (
        expected[0] * FULL_COMPENSATION
        + expected[1] * REDUCED_COMPENSATION_1
        + expected[2] * REDUCED_COMPENSATION_2
    )

    accrued_balance += penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert accrued_balance == expected_compensation
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after - before == expected_compensation
