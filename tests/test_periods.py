import ape
import pytest

PERIOD_DURATION = 3600  # 1 hour


@pytest.fixture(scope="module")
def deployer(accounts):
    return accounts[0]

@pytest.fixture(scope="module")
def periods_deployment(chain, deployer, project):
    genesis_time = chain.pending_timestamp
    contract = project.Periods.deploy(genesis_time, PERIOD_DURATION, sender=deployer)
    return genesis_time, contract

@pytest.fixture(scope="module")
def genesis(periods_deployment):
    genesis_time, _ = periods_deployment
    return genesis_time


@pytest.fixture(scope="module")
def periods(project, deployer, genesis):
    """Periods contract with fixed genesis and period duration."""
    contract = project.Periods.deploy(genesis, PERIOD_DURATION, sender=deployer)
    return contract


def test_constructor_invalid_period_duration(project, deployer, chain):
    with ape.reverts("Invalid period duration"):
        project.Periods.deploy(chain.pending_timestamp, 0, sender=deployer)


def test_immutables(periods, genesis):
    assert periods.GENESIS_TIME() == genesis
    assert periods.PERIOD_DURATION() == PERIOD_DURATION


def test_get_period_for_timestamp_before_genesis(periods, genesis):
    with ape.reverts("Timestamp is before genesis"):
        periods.getPeriodForTimestamp(genesis - 1)


def test_get_period_for_timestamp_at_genesis(periods, genesis):
    assert periods.getPeriodForTimestamp(genesis) == 0


def test_get_period_for_timestamp_after_periods(periods, genesis):
    duration = periods.PERIOD_DURATION()
    assert periods.getPeriodForTimestamp(genesis + duration - 1) == 0
    assert periods.getPeriodForTimestamp(genesis + duration) == 1
    assert periods.getPeriodForTimestamp(genesis + 2 * duration) == 2
    assert periods.getPeriodForTimestamp(genesis + 5 * duration + 1) == 5


def test_get_current_period(periods, chain, genesis):
    """getCurrentPeriod uses block.timestamp; we set chain time to align with genesis then advance."""
    duration = periods.PERIOD_DURATION()

    # TODO: eth-tester limitations prevent us from traveling back in time.
    # A proper test would imply a mock Periods contract that allows us to set the timestamp directly, rather than relying on chain time manipulation.
    # For now, not worth it.
    # chain.pending_timestamp = genesis
    # assert periods.getCurrentPeriod() == 0

    chain.pending_timestamp += duration
    assert periods.getCurrentPeriod() == 1
    chain.pending_timestamp += 2 * duration
    assert periods.getCurrentPeriod() == 3
