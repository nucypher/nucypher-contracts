from enum import IntEnum

import ape
import pytest
from ape.utils.misc import ZERO_ADDRESS
from web3 import Web3

DAY_IN_SECONDS = 60 * 60 * 24
TOTAL_SUPPLY = Web3.to_wei(11_000_000_000, "ether")

SigningCohortState = IntEnum(
    "SigningCohortState",
    ["NON_INITIATED", "AWAITING_SIGNATURES", "TIMEOUT", "ACTIVE", "EXPIRED"],
    start=0,
)

COHORT_SIZE = 8
DEFAULT_THRESHOLD = COHORT_SIZE // 2
DEFAULT_DURATION_IN_S = DAY_IN_SECONDS * 90  # 90 days
INIT_FEE_RATE_PER_SECOND = 1000
EXTEND_FEE_RATE_PER_SECOND = 1500


@pytest.fixture(scope="module")
def nodes(accounts):
    return [n.address for n in sorted(accounts[:COHORT_SIZE], key=lambda x: x.address.lower())]


@pytest.fixture()
def deployer(accounts):
    return accounts[COHORT_SIZE]


@pytest.fixture()
def token(project, deployer):
    # Create an ERC20 token
    token = deployer.deploy(project.TestToken, TOTAL_SUPPLY)
    return token


@pytest.fixture()
def other_accounts(accounts):
    return accounts[COHORT_SIZE + 1 :]


@pytest.fixture()
def signing_coordinator(project, deployer):
    contract = project.MockSigningCoordinatorForInitiator.deploy(sender=deployer)
    return contract


@pytest.fixture()
def signing_cohort_initiator(project, oz_dependency, signing_coordinator, token, nodes, deployer):
    contract_impl = project.SigningCohortInitiator.deploy(
        signing_coordinator.address,
        token.address,
        sender=deployer,
    )

    encoded_initializer_function = contract_impl.initialize.encode_input()
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract_impl.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    contract = project.SigningCohortInitiator.at(proxy.address)

    contract.setFeeRates(INIT_FEE_RATE_PER_SECOND, EXTEND_FEE_RATE_PER_SECOND, sender=deployer)
    contract.setDefaultParameters(
        nodes,
        DEFAULT_THRESHOLD,
        DEFAULT_DURATION_IN_S,
        sender=deployer,
    )

    return contract


@pytest.mark.parametrize(
    "fee_rate_per_second, duration",
    [
        (39, DAY_IN_SECONDS * 30),
        (60, DAY_IN_SECONDS * 90),
        (120, DAY_IN_SECONDS * 180),
        (1000, DAY_IN_SECONDS * 365),
    ],
)
def test_cohort_cost(fee_rate_per_second, duration, nodes, signing_cohort_initiator):
    cost = signing_cohort_initiator.getCohortCost(fee_rate_per_second, duration)
    assert cost == (len(nodes) * duration * fee_rate_per_second)


def test_establish_signing_cohort(
    signing_cohort_initiator, signing_coordinator, token, nodes, other_accounts
):
    initiator_1, initiator_2, authority_1, authority_2, *remaining = other_accounts

    cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )

    # Can't register request without token transfer approval
    with ape.reverts():
        signing_cohort_initiator.establishSigningCohort(authority_1, 1, sender=initiator_1)
    with ape.reverts():
        signing_cohort_initiator.establishSigningCohort(authority_2, 1, sender=initiator_2)

    token.mint(initiator_1, 5 * cohort_cost, sender=initiator_1)
    token.mint(initiator_2, 5 * cohort_cost, sender=initiator_2)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator_1)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator_2)

    for i, entry in enumerate([(initiator_1, authority_1, 10), (initiator_2, authority_2, 25)]):
        initiator, authority, chain_id = entry
        cohort_id = i
        assert (
            signing_coordinator.getSigningCohortState(cohort_id) == SigningCohortState.NON_INITIATED
        )

        initiator_balance_before = token.balanceOf(initiator)
        signing_coordinator_initiator_balance_before = token.balanceOf(
            signing_cohort_initiator.address
        )

        tx = signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)
        # payment processed
        assert token.balanceOf(initiator) == initiator_balance_before - cohort_cost
        assert (
            token.balanceOf(signing_cohort_initiator.address)
            == signing_coordinator_initiator_balance_before + cohort_cost
        )

        # request stored in initiator
        assert signing_cohort_initiator.requests(cohort_id) == (initiator.address, chain_id)

        # signing coordinator called
        assert (
            signing_coordinator.getSigningCohortState(cohort_id)
            == SigningCohortState.AWAITING_SIGNATURES
        )
        cohort = signing_coordinator.signingCohorts(cohort_id)
        assert cohort.initiator == signing_cohort_initiator.address
        assert cohort.authority == authority.address
        assert signing_coordinator.getChains(cohort_id) == [chain_id]
        assert cohort.threshold == DEFAULT_THRESHOLD

        # event emitted with correct values
        events = signing_cohort_initiator.RequestExecuted.from_receipt(tx)
        assert len(events) == 1
        event = events[0]
        assert event.cohortId == i
        assert event.initiator == initiator.address
        assert event.authority == authority.address
        assert event.chainId == chain_id


def test_deploy_additional_chain(
    signing_cohort_initiator, signing_coordinator, token, nodes, other_accounts, deployer
):
    initiator, authority, initiator_2, *remaining = other_accounts

    # Can't deploy chain for non-existent cohort
    with ape.reverts("Invalid cohort ID"):
        signing_cohort_initiator.deployAdditionalChain(0, 1, sender=initiator)

    # establish cohort
    initiator, authority = other_accounts[0], other_accounts[2]
    chain_id = 10
    new_chain_id = 25

    cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )
    token.mint(initiator, 5 * cohort_cost, sender=initiator)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator)

    signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)
    cohort_id = 0
    assert (
        signing_coordinator.getSigningCohortState(cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )

    # can't deploy additional chain for non-active ritual
    for state in list(SigningCohortState):
        if state == SigningCohortState.ACTIVE:
            continue

        signing_coordinator.setCohortState(cohort_id, state, sender=deployer)

        with ape.reverts("Cohort is not active"):
            signing_cohort_initiator.deployAdditionalChain(
                cohort_id, new_chain_id, sender=initiator
            )

    # mimic completion of ritual
    signing_coordinator.setCohortState(cohort_id, SigningCohortState.ACTIVE, sender=deployer)

    # can't deploy same chain as additional
    with ape.reverts("Chain ID already exists for this cohort"):
        signing_cohort_initiator.deployAdditionalChain(cohort_id, chain_id, sender=initiator)

    # must be original initiator to deploy additional chain
    with ape.reverts("Only initiator can deploy additional chain"):
        signing_cohort_initiator.deployAdditionalChain(cohort_id, chain_id, sender=initiator_2)

    # Deploy additional chain
    tx = signing_cohort_initiator.deployAdditionalChain(cohort_id, new_chain_id, sender=initiator)

    # Chain added to coordinator
    assert signing_coordinator.getChains(cohort_id) == [chain_id, new_chain_id]

    # Event emitted with correct values
    events = signing_cohort_initiator.AdditionalChainDeployed.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.cohortId == cohort_id
    assert event.chainId == new_chain_id


def test_extend_signing_cohort(
    signing_cohort_initiator, signing_coordinator, token, nodes, other_accounts, deployer
):
    initiator, authority, initiator_2, *remaining = other_accounts
    extension_duration = 365 * DAY_IN_SECONDS

    # Can't extend non-existent cohort
    with ape.reverts("Invalid cohort ID"):
        signing_cohort_initiator.extendSigningCohort(0, extension_duration, sender=initiator)

    # establish cohort
    initiator, authority, *remaining = other_accounts
    chain_id = 10

    cohort_cost = signing_cohort_initiator.getCohortCost(
        EXTEND_FEE_RATE_PER_SECOND, extension_duration
    )
    token.mint(initiator, 5 * cohort_cost, sender=initiator)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator)

    signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)
    cohort_id = 0
    assert (
        signing_coordinator.getSigningCohortState(cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )

    # can't extend non-active ritual
    for state in list(SigningCohortState):
        if state == SigningCohortState.ACTIVE:
            continue

        signing_coordinator.setCohortState(cohort_id, state, sender=initiator)

        with ape.reverts("Cohort is not active"):
            signing_cohort_initiator.extendSigningCohort(
                cohort_id, extension_duration, sender=deployer
            )

    # mimic completion of ritual
    signing_coordinator.setCohortState(cohort_id, SigningCohortState.ACTIVE, sender=deployer)

    original_end_timestamp = signing_coordinator.signingCohorts(cohort_id).endTimestamp

    # must be original initiator to extend
    with ape.reverts("Only initiator can extend cohort duration"):
        signing_cohort_initiator.extendSigningCohort(
            cohort_id, extension_duration, sender=initiator_2
        )

    with ape.reverts("Invalid duration"):
        # duration of 0
        signing_cohort_initiator.extendSigningCohort(cohort_id, 0, sender=initiator)

    with ape.reverts("Invalid duration"):
        # duration > 1 year
        signing_cohort_initiator.extendSigningCohort(
            cohort_id, 366 * DAY_IN_SECONDS, sender=initiator
        )

    # Extend cohort
    tx = signing_cohort_initiator.extendSigningCohort(
        cohort_id, extension_duration, sender=initiator
    )

    # Event emitted with correct values
    events = signing_cohort_initiator.ExtensionExecuted.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.cohortId == cohort_id
    assert event.additionalDuration == extension_duration
    new_end_timestamp = signing_coordinator.signingCohorts(cohort_id).endTimestamp
    assert new_end_timestamp == original_end_timestamp + extension_duration


def test_withdraw_fees(
    signing_cohort_initiator, signing_coordinator, other_accounts, token, nodes, deployer
):
    initiator, authority, owner, *remaining = other_accounts
    chain_id = 23

    signing_cohort_initiator.transferOwnership(owner, sender=deployer)

    # can only be called by owner
    with ape.reverts():
        signing_cohort_initiator.withdrawFees(sender=initiator)

    with ape.reverts("No fees to withdraw"):
        signing_cohort_initiator.withdrawFees(sender=owner)

    cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )

    num_cohorts = 5

    token.mint(initiator, (num_cohorts + 1) * cohort_cost, sender=initiator)
    token.approve(
        signing_cohort_initiator.address, (num_cohorts + 1) * cohort_cost, sender=initiator
    )

    for i in range(num_cohorts):
        cohort_id = i
        assert (
            signing_coordinator.getSigningCohortState(cohort_id) == SigningCohortState.NON_INITIATED
        )

        signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)

        assert (
            signing_coordinator.getSigningCohortState(cohort_id)
            == SigningCohortState.AWAITING_SIGNATURES
        )

    # fees are immediately available
    signing_coordinator_initiator_balance_before = token.balanceOf(signing_cohort_initiator.address)

    signing_cohort_initiator.withdrawFees(sender=owner)
    assert token.balanceOf(owner) == cohort_cost * num_cohorts
    assert token.balanceOf(
        signing_cohort_initiator.address
    ) == signing_coordinator_initiator_balance_before - (num_cohorts * cohort_cost)


def test_retry_failed_request(
    signing_cohort_initiator, signing_coordinator, token, nodes, other_accounts, deployer
):
    initiator, authority, initiator_2, *remaining = other_accounts
    chain_id = 23
    cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )

    token.mint(initiator, 5 * cohort_cost, sender=initiator)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator)

    cohort_id = 0
    assert signing_coordinator.getSigningCohortState(cohort_id) == SigningCohortState.NON_INITIATED

    initiator_balance_before = token.balanceOf(initiator)
    signing_coordinator_initiator_balance_before = token.balanceOf(signing_cohort_initiator.address)

    signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)

    # payment already processed
    assert token.balanceOf(initiator) == initiator_balance_before - cohort_cost
    assert (
        token.balanceOf(signing_cohort_initiator.address)
        == signing_coordinator_initiator_balance_before + cohort_cost
    )

    assert (
        signing_coordinator.getSigningCohortState(cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )

    # must be a valid cohort id
    with ape.reverts("Invalid cohort ID"):
        signing_cohort_initiator.retryFailedRequest(999, sender=initiator)

    # can't retry non-failed request
    with ape.reverts("Request did not fail"):
        signing_cohort_initiator.retryFailedRequest(cohort_id, sender=initiator)

    # check other states
    for state in list(SigningCohortState):
        if state == SigningCohortState.TIMEOUT:
            continue

        signing_coordinator.setCohortState(cohort_id, state, sender=deployer)
        with ape.reverts("Request did not fail"):
            signing_cohort_initiator.retryFailedRequest(cohort_id, sender=initiator)

    signing_coordinator.setCohortState(cohort_id, SigningCohortState.TIMEOUT, sender=deployer)

    # only initiator can request retry
    with ape.reverts("Only initiator can request retry"):
        signing_cohort_initiator.retryFailedRequest(cohort_id, sender=initiator_2)

    # Request retry
    initiator_balance_before_retry = token.balanceOf(initiator.address)
    signing_coordinator_initiator_balance_before = token.balanceOf(signing_cohort_initiator.address)
    tx = signing_cohort_initiator.retryFailedRequest(cohort_id, sender=initiator)

    # payment already made from failed request; no additional payment required for retry
    assert (
        token.balanceOf(initiator.address) == initiator_balance_before_retry
    ), "no change in balance"
    assert (
        token.balanceOf(signing_cohort_initiator.address)
        == signing_coordinator_initiator_balance_before
    ), "no change in balance"

    events = signing_cohort_initiator.RetryFailedRequest.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.oldCohortId == cohort_id
    assert event.newCohortId > cohort_id

    new_cohort_id = event.newCohortId

    # New request stored
    assert signing_cohort_initiator.requests(new_cohort_id) == (initiator.address, chain_id)
    assert (
        signing_coordinator.getSigningCohortState(new_cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )

    # entry for old cohort removed
    assert signing_cohort_initiator.requests(cohort_id) == (ZERO_ADDRESS, 0)


def test_set_default_parameters(
    signing_cohort_initiator, signing_coordinator, token, nodes, other_accounts, deployer
):
    initiator, authority, authority_2, *remaining = other_accounts
    chain_id = 23
    cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )

    token.mint(initiator, 5 * cohort_cost, sender=initiator)
    token.approve(signing_cohort_initiator.address, 5 * cohort_cost, sender=initiator)

    cohort_id = 0
    assert signing_coordinator.getSigningCohortState(cohort_id) == SigningCohortState.NON_INITIATED

    signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)

    assert (
        signing_coordinator.getSigningCohortState(cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )

    signing_cohort = signing_coordinator.signingCohorts(cohort_id)
    assert signing_cohort.threshold == DEFAULT_THRESHOLD
    assert signing_cohort.endTimestamp == signing_cohort.initTimestamp + DEFAULT_DURATION_IN_S
    assert set(signing_coordinator.getProviders(cohort_id)) == set(nodes)
    assert signing_cohort.authority == authority

    # update default parameters
    new_threshold = 2
    new_nodes = [n.address for n in sorted(remaining[:5], key=lambda x: x.address.lower())]
    new_duration = DAY_IN_SECONDS * 10

    tx = signing_cohort_initiator.setDefaultParameters(
        new_nodes, new_threshold, new_duration, sender=deployer
    )
    events = signing_cohort_initiator.DefaultParametersUpdated.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.providers == new_nodes
    assert event.threshold == new_threshold
    assert event.duration == new_duration

    assert signing_cohort_initiator.getCohortCost(INIT_FEE_RATE_PER_SECOND, new_duration) == (
        len(new_nodes) * new_duration * INIT_FEE_RATE_PER_SECOND
    )

    # request new cohort
    signing_cohort_initiator.establishSigningCohort(authority_2, chain_id, sender=initiator)
    new_cohort_id = 1
    assert (
        signing_coordinator.getSigningCohortState(new_cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )
    new_signing_cohort = signing_coordinator.signingCohorts(new_cohort_id)
    assert new_signing_cohort.threshold == new_threshold
    assert new_signing_cohort.endTimestamp == new_signing_cohort.initTimestamp + new_duration
    assert set(signing_coordinator.getProviders(new_cohort_id)) == set(new_nodes)
    assert new_signing_cohort.authority == authority_2

    # old cohort remains unchanged
    signing_cohort = signing_coordinator.signingCohorts(cohort_id)
    assert signing_cohort.threshold == DEFAULT_THRESHOLD
    assert signing_cohort.endTimestamp == signing_cohort.initTimestamp + DEFAULT_DURATION_IN_S
    assert set(signing_coordinator.getProviders(cohort_id)) == set(nodes)
    assert signing_cohort.authority == authority


def test_set_fee_rates_per_second(
    signing_cohort_initiator, signing_coordinator, deployer, token, nodes, other_accounts
):
    init_cohort_cost = signing_cohort_initiator.getCohortCost(
        INIT_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )
    assert init_cohort_cost == len(nodes) * DEFAULT_DURATION_IN_S * INIT_FEE_RATE_PER_SECOND

    extend_cohort_cost = signing_cohort_initiator.getCohortCost(
        EXTEND_FEE_RATE_PER_SECOND, DEFAULT_DURATION_IN_S
    )
    assert extend_cohort_cost == len(nodes) * DEFAULT_DURATION_IN_S * EXTEND_FEE_RATE_PER_SECOND
    assert extend_cohort_cost != init_cohort_cost

    with ape.reverts("Extension rate less than initiation rate"):
        signing_cohort_initiator.setFeeRates(
            INIT_FEE_RATE_PER_SECOND, INIT_FEE_RATE_PER_SECOND - 1, sender=deployer
        )

    new_init_fee_rate_per_second = INIT_FEE_RATE_PER_SECOND * 2
    new_extend_fee_rate_per_second = EXTEND_FEE_RATE_PER_SECOND * 4
    tx = signing_cohort_initiator.setFeeRates(
        new_init_fee_rate_per_second, new_extend_fee_rate_per_second, sender=deployer
    )

    assert signing_cohort_initiator.initFeeRatePerSecond() == new_init_fee_rate_per_second
    assert signing_cohort_initiator.extendFeeRatePerSecond() == new_extend_fee_rate_per_second

    events = signing_cohort_initiator.InitFeeRateUpdated.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.oldFeeRate == INIT_FEE_RATE_PER_SECOND
    assert event.newFeeRate == new_init_fee_rate_per_second

    # initiation fees
    new_init_cohort_cost = signing_cohort_initiator.getCohortCost(
        new_init_fee_rate_per_second, DEFAULT_DURATION_IN_S
    )
    assert new_init_cohort_cost != init_cohort_cost
    assert new_init_cohort_cost == len(nodes) * DEFAULT_DURATION_IN_S * new_init_fee_rate_per_second

    events = signing_cohort_initiator.ExtendFeeRateUpdated.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event.oldFeeRate == EXTEND_FEE_RATE_PER_SECOND
    assert event.newFeeRate == new_extend_fee_rate_per_second

    # extension fees
    extension_duration = 360 * DAY_IN_SECONDS

    new_extend_cohort_cost = signing_cohort_initiator.getCohortCost(
        new_extend_fee_rate_per_second, extension_duration
    )
    assert new_extend_cohort_cost != new_init_cohort_cost
    assert new_extend_cohort_cost != extend_cohort_cost
    assert (
        new_extend_cohort_cost == len(nodes) * extension_duration * new_extend_fee_rate_per_second
    )

    # try initiating and extending cohort with new fee rates
    initiator, authority, *remaining = other_accounts
    token.mint(initiator, 5 * new_extend_cohort_cost, sender=initiator)
    token.approve(signing_cohort_initiator.address, 5 * new_extend_cohort_cost, sender=initiator)

    initiator_balance_before = token.balanceOf(initiator)
    signing_coordinator_initiator_balance_before = token.balanceOf(signing_cohort_initiator.address)

    chain_id = 10
    _ = signing_cohort_initiator.establishSigningCohort(authority, chain_id, sender=initiator)
    cohort_id = 0

    # initiation payment processed
    assert token.balanceOf(initiator) == initiator_balance_before - new_init_cohort_cost
    assert (
        token.balanceOf(signing_cohort_initiator.address)
        == signing_coordinator_initiator_balance_before + new_init_cohort_cost
    )
    assert (
        signing_coordinator.getSigningCohortState(cohort_id)
        == SigningCohortState.AWAITING_SIGNATURES
    )
    # mimic completion of ritual
    signing_coordinator.setCohortState(cohort_id, SigningCohortState.ACTIVE, sender=deployer)

    # Extend cohort
    initiator_balance_before = token.balanceOf(initiator)
    signing_coordinator_initiator_balance_before = token.balanceOf(signing_cohort_initiator.address)

    _ = signing_cohort_initiator.extendSigningCohort(
        cohort_id, extension_duration, sender=initiator
    )
    # extension payment processed
    assert token.balanceOf(initiator) == initiator_balance_before - new_extend_cohort_cost
    assert (
        token.balanceOf(signing_cohort_initiator.address)
        == signing_coordinator_initiator_balance_before + new_extend_cohort_cost
    )
