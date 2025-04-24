import pytest
from eth_abi import encode
from eth_account.messages import encode_defunct
from web3 import Web3

from tests.conftest import SigningRitualState

TIMEOUT = 1000
MAX_DKG_SIZE = 31
DURATION = 48 * 60 * 60


@pytest.fixture(scope="module")
def nodes(accounts):
    return sorted(accounts[:MAX_DKG_SIZE], key=lambda x: x.address.lower())


@pytest.fixture(scope="module")
def initiator(accounts):
    initiator_index = MAX_DKG_SIZE + 1
    assert len(accounts) >= initiator_index
    return accounts[initiator_index]


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer_index = MAX_DKG_SIZE + 2
    assert len(accounts) >= deployer_index
    return accounts[deployer_index]


@pytest.fixture(scope="module")
def treasury(accounts):
    treasury_index = MAX_DKG_SIZE + 3
    assert len(accounts) >= treasury_index
    return accounts[treasury_index]


@pytest.fixture()
def application(project, deployer, nodes):
    contract = project.ChildApplicationForCoordinatorMock.deploy(sender=deployer)
    for n in nodes:
        contract.updateOperator(n, n, sender=deployer)
        contract.updateAuthorization(n, 42, sender=deployer)
    return contract


@pytest.fixture()
def threshold_signing_multisig(project, deployer):
    contract = project.ThresholdSigningMultisig.deploy(
        sender=deployer,
    )
    return contract


@pytest.fixture()
def threshold_signing_multisig_clone_factory(project, deployer, threshold_signing_multisig):
    contract = project.ThresholdSigningMultisigCloneFactory.deploy(
        threshold_signing_multisig.address,
        sender=deployer,
    )

    return contract


@pytest.fixture()
def signing_coordinator(
    project, deployer, application, threshold_signing_multisig_clone_factory, oz_dependency
):
    admin = deployer
    contract = project.SigningCoordinator.deploy(
        application.address,
        threshold_signing_multisig_clone_factory.address,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(TIMEOUT, MAX_DKG_SIZE, admin)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.SigningCoordinator.at(proxy.address)
    return proxy_contract


#
# Signing
#


def test_signing_ritual(
    project, signing_coordinator, threshold_signing_multisig_clone_factory, initiator, nodes
):
    threshold = len(nodes) // 2 + 1
    tx = signing_coordinator.initiateSigningCohort(
        initiator, nodes, threshold, DURATION, sender=initiator
    )

    signing_cohort_id = 0
    events = [event for event in tx.events if event.event_name == "InitiateSigningCohort"]
    assert len(events) == 1
    event = events[0]
    assert event.cohortId == signing_cohort_id
    assert event.authority == initiator
    assert event.participants == [n.address for n in nodes]

    signing_cohort_struct = signing_coordinator.signingCohorts(signing_cohort_id)
    assert signing_cohort_struct["initiator"] == initiator
    init, end = signing_cohort_struct[1], signing_cohort_struct["endTimestamp"]
    assert end - init == DURATION
    assert signing_cohort_struct["authority"] == initiator
    assert signing_cohort_struct["totalSignatures"] == 0

    assert signing_cohort_struct["numSigners"] == len(nodes)
    assert signing_cohort_struct["threshold"] == threshold

    for n in nodes:
        assert signing_coordinator.isSigner(signing_cohort_id, n.address)

    assert (
        signing_coordinator.getSigningCohortState(signing_cohort_id)
        == SigningRitualState.AWAITING_SIGNATURES
    )

    # submit signatures
    for i, node in enumerate(nodes):
        data = encode(["uint32", "address"], [signing_cohort_id, initiator.address])
        digest = Web3.keccak(data)
        signable_message = encode_defunct(digest)
        signature = node.sign_message(signable_message).encode_rsv()
        tx = signing_coordinator.postSigningCohortSignature(
            signing_cohort_id, signature, sender=node
        )

        events = [
            event for event in tx.events if event.event_name == "SigningCohortSignaturePosted"
        ]
        assert events == [
            signing_coordinator.SigningCohortSignaturePosted(
                cohortId=signing_cohort_id, provider=node, signature=signature
            )
        ]

    assert signing_coordinator.getSigningCohortState(signing_cohort_id) == SigningRitualState.ACTIVE
    assert signing_coordinator.isCohortActive(signing_cohort_id)
    for i, node in enumerate(nodes):
        assert signing_coordinator.isSigner(signing_cohort_id, node.address)
        signer = signing_coordinator.getSigner(signing_cohort_id, node.address)
        assert signer.provider == node.address
        assert len(signer.signature) > 0, "signature posted"

    # check deployed multisig
    expected_multisig_address = threshold_signing_multisig_clone_factory.getCloneAddress(
        signing_cohort_id
    )

    signing_cohort_struct = signing_coordinator.signingCohorts(signing_cohort_id)
    assert signing_cohort_struct["multisig"] == expected_multisig_address

    events = [event for event in tx.events if event.event_name == "SigningCohortCompleted"]
    assert events == [
        signing_coordinator.SigningCohortCompleted(
            cohortId=signing_cohort_id,
            multisig=expected_multisig_address,
        )
    ]

    cohort_multisig = project.ThresholdSigningMultisig.at(expected_multisig_address)
    assert cohort_multisig.getSigners() == [n.address for n in nodes]
    assert cohort_multisig.threshold() == threshold
    assert cohort_multisig.owner() == initiator.address
