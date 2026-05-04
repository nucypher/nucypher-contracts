import ape
import pytest

from ape.utils import ZERO_ADDRESS


PERIOD_DURATION = 3600
FULL_COMPENSATION = 1000
REDUCED_COMPENSATION_1 = 600
REDUCED_COMPENSATION_2 = 100
TOKEN_SUPPLY = 1_000_000 * 10**18
MAX_UINT256 = 2**256 - 1
REWARD_DELAY_PERIODS = 2


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
def owner(accounts):
    return accounts[5]


@pytest.fixture(scope="module")
def other_account(accounts):
    return accounts[6]


@pytest.fixture(scope="module")
def stakeless_provider(accounts):
    return accounts[7]


@pytest.fixture(scope="module")
def mock_taco_app(project, deployer):
    return project.MockTACoForPenaltyBoard.deploy(sender=deployer)


@pytest.fixture(scope="module")
def token(project, deployer):
    return project.TestToken.deploy(TOKEN_SUPPLY, sender=deployer)


@pytest.fixture
def penalty_board_comp(project, deployer, informer, chain, mock_taco_app, token, fund_holder):
    """PenaltyBoard with compensation enabled (7-arg constructor)."""
    genesis_time = chain.pending_timestamp - 2 * PERIOD_DURATION
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
        REWARD_DELAY_PERIODS,
        sender=deployer,
    )
    contract.grantRole(contract.INFORMER_ROLE(), informer.address, sender=deployer)
    token.transfer(fund_holder.address, 100 * FULL_COMPENSATION, sender=deployer)
    token.approve(contract.address, MAX_UINT256, sender=fund_holder)
    mock_taco_app.setPenaltyBoard(contract.address, sender=deployer)
    return contract


@pytest.fixture
def registered_staker(mock_taco_app, staking_provider, owner, beneficiary, deployer):
    """Register staking_provider in mock TACo: owner=owner, beneficiary=beneficiary, not stakeless."""
    mock_taco_app.setRoles(
        staking_provider.address,
        owner.address,
        beneficiary.address,
        False, # not stakeless
        True, # rewards enabled
        sender=deployer,
    )
    return staking_provider


@pytest.fixture
def registered_stakeless(mock_taco_app, stakeless_provider, owner, deployer):
    """Register stakeless_provider in mock TACo: owner=owner, stakeless."""
    mock_taco_app.setRoles(
        stakeless_provider.address,
        owner.address,
        ZERO_ADDRESS,  # beneficiary is zero address since stakeless staker should not be able to accrue rewards
        True,  # stakeless
        False, # rewards disabled since stakeless staker should not be able to accrue rewards
        sender=deployer,
    )
    return stakeless_provider


@pytest.fixture
def registered_no_reward(mock_taco_app, stakeless_provider, owner, beneficiary, deployer):
    """Register provider in mock TACo: owner=owner, beneficiary=beneficiary, stakeless."""
    mock_taco_app.setRoles(
        stakeless_provider.address,
        owner.address,
        beneficiary.address,
        False, # not stakeless
        False, # rewards disabled since this staker should not be able to accrue rewards
        sender=deployer,
    )
    return stakeless_provider


def test_penalized_periods_by_staker_updated(
    penalty_board_comp, informer, staking_provider, other_account
):
    """addPenalizedProvidersForPeriod(provs, period) causes penalizedPeriodsByStaker[prov] to include period."""
    current = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    penalty_board_comp.addPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [current]

    provs = [other_account.address]
    penalty_board_comp.addPenalizedProvidersForPeriod(provs, current, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [current]


def test_penalized_periods_monotonic_append(penalty_board_comp, informer, staking_provider, chain):
    """Calling addPenalizedProvidersForPeriod for different periods appends to each staker's list (monotonic)."""
    current = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    penalty_board_comp.addPenalizedProvidersForPeriod(provs, current, sender=informer)
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == current + 1
    penalty_board_comp.addPenalizedProvidersForPeriod(provs, current + 1, sender=informer)
    assert penalty_board_comp.getPenalizedPeriodsByStaker(staking_provider.address) == [
        current,
        current + 1,
    ]


def test_penalized_periods_disallow_unordered_append(penalty_board_comp, informer, staking_provider, chain):
    """Calling addPenalizedProvidersForPeriod for different periods must be in order; reverts if period is not > last period for that staker."""
    first_period = penalty_board_comp.getCurrentPeriod()
    provs = [staking_provider.address]
    
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == first_period + 1

    penalty_board_comp.addPenalizedProvidersForPeriod(provs, first_period + 1, sender=informer)
    with ape.reverts("Periods must be added in order"):
        penalty_board_comp.addPenalizedProvidersForPeriod(provs, first_period, sender=informer)


def test_withdraw_reverts_unauthorized_for_stakeless(
    penalty_board_comp, registered_stakeless, chain, beneficiary, deployer
):
    """Withdraw reverts with 'Unauthorized' for stakeless staker even if beneficiary or owner tries to call withdraw."""
    with ape.reverts("Unauthorized"):
        penalty_board_comp.withdraw(registered_stakeless.address, sender=beneficiary)
    with ape.reverts("Unauthorized"):
        penalty_board_comp.withdraw(registered_stakeless.address, sender=deployer)


def test_withdraw_reverts_nothing_to_withdraw_for_stakeless(
    penalty_board_comp, registered_stakeless, chain, beneficiary, deployer, owner
):
    """Withdraw reverts with 'Nothing to withdraw' for stakeless staker even if beneficiary or owner tries to call withdraw."""
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(registered_stakeless.address, sender=registered_stakeless)
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(registered_stakeless.address, sender=owner)
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(registered_stakeless.address, sender=owner)


def test_withdraw_reverts_nothing_to_withdraw_for_no_reward(
    penalty_board_comp, registered_no_reward, chain, beneficiary
):
    """Withdraw reverts with 'Nothing to withdraw' for staker with no rewards."""
    with ape.reverts("Nothing to withdraw"):
        penalty_board_comp.withdraw(registered_no_reward.address, sender=beneficiary)


def test_get_accrued_balance_reflects_periods_without_prior_withdraw(
    penalty_board_comp, registered_staker, chain
):
    """getAccruedBalance returns accrued amount for periods 0..current when staker has not yet withdrawn."""
    # At deploy we are in period 2, so there's nothing to accrue yet (accrual lag is 2 periods)
    balance = penalty_board_comp.getAccruedBalance(registered_staker.address)
    assert penalty_board_comp.getCurrentPeriod() == 2
    assert balance == 0

    # After advancing 1 period, there's still nothing to accrue (accrual lag is 2 periods)
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == 3
    balance = penalty_board_comp.getAccruedBalance(registered_staker.address)
    assert balance == 0

    # After advancing 1 more period (2 total), we should accrue for period 2
    chain.pending_timestamp += PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == 4
    balance = penalty_board_comp.getAccruedBalance(registered_staker.address)
    assert balance == FULL_COMPENSATION


def test_accrual_with_no_penalties_gives_full_compensation(
    penalty_board_comp, chain, staking_provider, registered_staker
):
    """After advancing periods with no penalties, staker should have positive accrued balance"""
    # Advance 2 periods so there is something to accrue
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert (
        balance == FULL_COMPENSATION
    ), "Incorrect accrual: getAccruedBalance should be > 0 after 2 periods with no penalties"


def test_accrual_with_one_penalty_gives_full_compensation(
    penalty_board_comp, chain, staking_provider, registered_staker, informer
):
    """After advancing periods with 1 penalty, staker should still have full accrued balance since penalty only reduces for more than 1 penalty in a period"""
    penalized_providers = [staking_provider.address]
    current = penalty_board_comp.getCurrentPeriod()
    penalty_board_comp.addPenalizedProvidersForPeriod(penalized_providers, current, sender=informer)
    # Advance 2 periods so there is something to accrue
    chain.pending_timestamp += 2 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert (
        balance == FULL_COMPENSATION
    ), "Incorrect accrual: getAccruedBalance should be > 0 after 2 periods with only 1 penalties"


def test_accrual_with_two_penalties_gives_reduced_compensation(
    penalty_board_comp, chain, staking_provider, registered_staker, informer
):
    """After advancing periods with 2 penalties, staker should have reduced accrued balance since penalty reduces for more than 1 penalty in a period"""
    penalized_providers = [staking_provider.address]
    current = penalty_board_comp.getCurrentPeriod()
    penalty_board_comp.addPenalizedProvidersForPeriod(penalized_providers, current, sender=informer)
    # Advance 1 period and add another penalty in the same period
    chain.pending_timestamp += PERIOD_DURATION
    penalty_board_comp.addPenalizedProvidersForPeriod(penalized_providers, current + 1, sender=informer)
    # Advance 1 more period so there is something to accrue
    chain.pending_timestamp += PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert (
        balance == FULL_COMPENSATION
    ), "Incorrect accrual: getAccruedBalance should be FULL_COMPENSATION after 2 periods with only 1 penalties"

    chain.pending_timestamp += PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert (
        balance == FULL_COMPENSATION + REDUCED_COMPENSATION_1
    ), "Incorrect accrual: getAccruedBalance should be > 0 after 2 periods with only 1 penalties"



def test_unauthorized_caller_cant_withdraw(
    penalty_board_comp, registered_staker, other_account, staking_provider
):
    """Only owner, staking provider, or beneficiary may call withdraw; others revert"""
    with ape.reverts("Unauthorized"):
        penalty_board_comp.withdraw(staking_provider.address, sender=other_account)


@pytest.mark.parametrize("caller", ["owner", "staking_provider", "beneficiary"])
def test_withdraw_sends_tokens_to_beneficiary(
    penalty_board_comp,
    token,
    fund_holder,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    caller,
    request,
):
    """Withdraw sends tokens to beneficiary, not to msg.sender"""
    # We parametrize over the 3 authorized caller types to confirm that tokens are sent to beneficiary regardless of which authorized caller calls withdraw
    caller = request.getfixturevalue(caller)
    # Advance so there is accrual
    chain.pending_timestamp += 3 * PERIOD_DURATION
    before = token.balanceOf(beneficiary.address)
    # Authorized caller calls withdraw for staking_provider
    penalty_board_comp.withdraw(staking_provider.address, sender=caller)
    after = token.balanceOf(beneficiary.address)
    assert after > before, "Withdraw should send tokens to beneficiary"


def test_stakeless_staker_gets_zero_compensation(penalty_board_comp, registered_stakeless, chain):
    """Stakeless staker accrues 0"""
    chain.pending_timestamp += 10 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(registered_stakeless.address)
    assert balance == 0, "Stakeless staker should have 0 accrued compensation"


def test_no_reward_staker_gets_zero_compensation(penalty_board_comp, registered_no_reward, chain):
    """No-reward staker accrues 0"""
    chain.pending_timestamp += 10 * PERIOD_DURATION
    balance = penalty_board_comp.getAccruedBalance(registered_no_reward.address)
    assert balance == 0, "No-reward staker should have 0 accrued compensation"


# --- Edge cases ---


def test_first_withdrawal_accrues_from_period_zero(
    penalty_board_comp,
    token,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
):
    """First withdrawal accrues from period 0 to current; full amount to beneficiary."""
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


@pytest.mark.parametrize("cadence", [(12,), (4, 5, 6, 7, 8, 9, 10, 11, 12), (1, 7, 12)])
def test_many_periods_full_accrual_regardless_of_withdraw_cadence(
    penalty_board_comp, token, beneficiary, staking_provider, registered_staker, chain, cadence
):
    """Many periods with no penalties: full accrual (numPeriods * fixed per period)."""
    n = 10
    last_period = n + 2

    # chain.pending_timestamp += 2 * PERIOD_DURATION
    # Periods 0..n → n+1 periods
    expected = (n - 1) * FULL_COMPENSATION
    initial_balance = token.balanceOf(beneficiary.address)
    for withdraw_period in cadence:
        current_period = penalty_board_comp.getCurrentPeriod()
        offset = withdraw_period - current_period
        if offset > 0:
            chain.pending_timestamp += offset * PERIOD_DURATION
            penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)

    assert penalty_board_comp.getCurrentPeriod() == last_period
    final_balance = token.balanceOf(beneficiary.address)
    assert final_balance - initial_balance == expected


@pytest.mark.parametrize(
    "periods",
    [
        # T F F F F T -> 0 1 2 3 4 3 -> F F R1 R2 0 R2
        {
            "penalized_periods": [1, 2, 3, 4],
            "expected_full": 2,
            "expected_reduced_1": 1,
            "expected_reduced_2": 2,
            "num_periods": 5,
            "intermediate_withdraws": [],
        },
        # F T T T F T -> 1 1 1 1 1 1 -> F F F F F F
        {
            "penalized_periods": [0, 4],
            "expected_full": 6,
            "expected_reduced_1": 0,
            "expected_reduced_2": 0,
            "num_periods": 5,
            "intermediate_withdraws": [2, 3, 4],
        },
        # T T T F F F T -> 0 0 0 1 2 3 3 -> F F F F R1 R2 R2
        {
            "penalized_periods": [3, 4, 5],
            "expected_full": 4,
            "expected_reduced_1": 1,
            "expected_reduced_2": 2,
            "num_periods": 6,
            "intermediate_withdraws": [2, 3, 4, 5],
        },
    ],
)
def test_penalty_in_range_reduces_compensation(
    penalty_board_comp,
    token,
    beneficiary,
    staking_provider,
    registered_staker,
    chain,
    informer,
    periods,
):
    """
    This test showcases several features of the compensation contract:
        - Penalties in a period reduce compensation for the window between affected period and the next PENALTY_WINDOW_PERIODS periods, but not for other periods
        - On each period, accrued amount depends on the penalty composition of the window
        - Only periods with 0 or 1 penalties in the window get full compensation; 2 penalties get a reduced compensation, 3 penalties a further reduced compensation, and 4 penalties no compensation.
        - Intermediate withdraws don't affect the overal accrued and witdrawn amount since accrued amount is always based on the full history of penalties and withdraw just takes the current accrued balance at the time of withdraw
    """
    penalized_periods = periods["penalized_periods"]
    expected_full = periods["expected_full"]
    expected_reduced_1 = periods["expected_reduced_1"]
    expected_reduced_2 = periods["expected_reduced_2"]
    num_periods = periods["num_periods"]
    intermediate_withdraws = periods["intermediate_withdraws"]

    before = token.balanceOf(beneficiary.address)

    penalty_index = 0
    withdraw_index = 0
    accrued_balance = 0
    first_period = 2
    for current_period in range(num_periods):
        if (
            withdraw_index < len(intermediate_withdraws)
            and intermediate_withdraws[withdraw_index] == current_period
        ):
            accrued_balance += penalty_board_comp.getAccruedBalance(staking_provider.address)
            penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
            withdraw_index += 1
        if (
            penalty_index < len(penalized_periods)
            and penalized_periods[penalty_index] == current_period
        ):
            penalty_board_comp.addPenalizedProvidersForPeriod(
                [staking_provider.address], current_period + first_period, sender=informer
            )
            penalty_index += 1

        chain.pending_timestamp += PERIOD_DURATION

    chain.pending_timestamp += 2 * PERIOD_DURATION

    expected_compensation = (
        expected_full * FULL_COMPENSATION
        + expected_reduced_1 * REDUCED_COMPENSATION_1
        + expected_reduced_2 * REDUCED_COMPENSATION_2
    )

    accrued_balance += penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert accrued_balance == expected_compensation
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after - before == expected_compensation


def test_turning_on_and_off_reward(
    penalty_board_comp,
    staking_provider,
    owner,
    beneficiary,
    deployer,
    token,
    registered_no_reward,
    mock_taco_app,
    chain,
):
    """Turning on and off reward accrual should affect compensation: staker should accrue when reward is on, and not accrue when reward is off."""
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == 0

    assert penalty_board_comp.getCurrentPeriod() == 2

    # Period 2, off -> period 3, on
    chain.pending_timestamp += PERIOD_DURATION
    mock_taco_app.enableRewards(staking_provider.address, sender=deployer)
    mock_taco_app.setRoles(
        staking_provider.address,
        owner.address,
        beneficiary.address,
        False, # Not stakeless
        True, # rewards enabled since this staker should accrue rewards for now
        sender=deployer,
    )

    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == 0

    # Period 3, on -> Period 5, off
    chain.pending_timestamp += 2 * PERIOD_DURATION
    mock_taco_app.computeRewards(staking_provider.address, sender=deployer)
    mock_taco_app.setRoles(
        staking_provider.address,
        owner.address,
        beneficiary.address,
        False,
        False,  # rewards disabled since this staker should not accrue rewards now
        sender=deployer,
    )

    assert penalty_board_comp.getCurrentPeriod() == 5
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == FULL_COMPENSATION

    # Period 5, off -> Period 6, on
    chain.pending_timestamp += PERIOD_DURATION
    mock_taco_app.enableRewards(staking_provider.address, sender=deployer)
    mock_taco_app.setRoles(
        staking_provider.address,
        owner.address,
        beneficiary.address,
        False,
        True,  # rewards enabled since this staker should accrue rewards now
        sender=deployer,
    )

    assert penalty_board_comp.getCurrentPeriod() == 6
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == FULL_COMPENSATION

    # Period 6, on -> Period 10, off
    chain.pending_timestamp += 4 * PERIOD_DURATION
    mock_taco_app.computeRewards(staking_provider.address, sender=deployer)
    mock_taco_app.setRoles(
        staking_provider.address,
        owner.address,
        beneficiary.address,
        False,
        False, # rewards disabled again
        sender=deployer,
    )

    expected = 4 * FULL_COMPENSATION
    assert penalty_board_comp.getCurrentPeriod() == 10
    balance = penalty_board_comp.getAccruedBalance(staking_provider.address)
    assert balance == expected

    # Period 10, off -> off going forward
    chain.pending_timestamp += 4 * PERIOD_DURATION
    assert penalty_board_comp.getCurrentPeriod() == 14
    before = token.balanceOf(beneficiary.address)
    penalty_board_comp.withdraw(staking_provider.address, sender=beneficiary)
    after = token.balanceOf(beneficiary.address)
    assert after - before == expected
