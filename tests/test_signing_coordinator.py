import pytest
from eth.constants import ZERO_ADDRESS
from eth_account.messages import _hash_eip191_message, encode_defunct
from web3 import Web3

from tests.conftest import ERC1271_INVALID_SIGNATURE, ERC1271_MAGIC_VALUE_BYTES, SigningRitualState

TIMEOUT = 1000
MAX_DKG_SIZE = 31
DURATION = 48 * 60 * 60

OTHER_CHAIN_ID_FOR_BRIDGE = 112233445566


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


@pytest.fixture()
def application(project, oz_dependency, deployer, accounts, nodes):
    threshold_staking = deployer.deploy(project.ThresholdStakingForTACoApplicationMock)

    token = deployer.deploy(project.TestToken, 1_000_000)

    min_auth = Web3.to_wei(40_000, "ether")
    taco_application_impl = deployer.deploy(
        project.TACoApplication,
        token.address,
        threshold_staking.address,
        min_auth,
        60 * 60 * 24,
        60 * 60 * 24 * 7,
        60 * 60 * 24 * 60,
        1000,
        60 * 60 * 24,
        2500,
    )
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        taco_application_impl.address,
        deployer,
        b"",
        sender=deployer,
    )
    taco_application = project.TACoApplication.at(proxy.address)

    threshold_staking.setApplication(taco_application.address, sender=deployer)
    taco_application.initialize(sender=deployer)

    child_application = project.ChildApplicationForTACoApplicationMock.deploy(
        taco_application.address, sender=deployer
    )
    taco_application.setChildApplication(child_application.address, sender=deployer)

    # setup stakes / nodes
    for n in nodes:
        threshold_staking.setRoles(n, sender=n)
        threshold_staking.authorizationIncreased(n, 0, min_auth, sender=n)
        taco_application.bondOperator(n, n, sender=n)
        child_application.confirmOperatorAddress(n, sender=deployer)

    return taco_application


def _signing_coordinator_child_deployment(project, oz_dependency, deployer):
    threshold_signing_multisig = project.ThresholdSigningMultisig.deploy(
        sender=deployer,
    )
    signing_factory_contract = project.ThresholdSigningMultisigCloneFactory.deploy(
        threshold_signing_multisig.address,
        sender=deployer,
    )

    contract = project.SigningCoordinatorChild.deploy(
        signing_factory_contract.address,
        sender=deployer,
    )

    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        b"",
        sender=deployer,
    )
    proxy_contract = project.SigningCoordinatorChild.at(proxy.address)

    return proxy_contract


@pytest.fixture()
def signing_coordinator_child(project, oz_dependency, deployer):
    return _signing_coordinator_child_deployment(project, oz_dependency, deployer)


@pytest.fixture()
def other_chain_signing_coordinator_child(project, oz_dependency, deployer):
    return _signing_coordinator_child_deployment(project, oz_dependency, deployer)


@pytest.fixture()
def mock_bridge_contracts(project, deployer):
    mock_bridge_messenger = deployer.deploy(project.MockOpBridgeMessenger)

    l2_receiver = deployer.deploy(project.OpL2Receiver, mock_bridge_messenger.address)

    l1_sender = deployer.deploy(
        project.OpL1Sender, mock_bridge_messenger.address, l2_receiver.address, 500_000
    )
    mock_bridge_messenger.initialize(l1_sender.address, sender=deployer)

    l2_receiver.initialize(l1_sender.address, sender=deployer)

    yield mock_bridge_messenger, l1_sender, l2_receiver


@pytest.fixture()
def signing_coordinator_dispatcher(
    project,
    oz_dependency,
    chain,
    deployer,
    signing_coordinator_child,
    other_chain_signing_coordinator_child,
    mock_bridge_contracts,
):
    contract = project.SigningCoordinatorDispatcher.deploy(
        sender=deployer,
    )

    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        b"",
        sender=deployer,
    )
    proxy_contract = project.SigningCoordinatorDispatcher.at(proxy.address)
    proxy_contract.initialize(sender=deployer)

    # don't need a L1Sender for the same chain as signing coordinator
    # current chain
    proxy_contract.register(
        chain.chain_id, ZERO_ADDRESS, signing_coordinator_child.address, sender=deployer
    )

    # need a L1Sender for the other chain
    _, l1_sender, _ = mock_bridge_contracts
    proxy_contract.register(
        OTHER_CHAIN_ID_FOR_BRIDGE,
        l1_sender.address,
        other_chain_signing_coordinator_child.address,
        sender=deployer,
    )

    return proxy_contract


@pytest.fixture()
def signing_coordinator(
    project,
    deployer,
    initiator,
    application,
    signing_coordinator_dispatcher,
    oz_dependency,
):
    admin = deployer
    contract = project.SigningCoordinator.deploy(
        application.address,
        signing_coordinator_dispatcher.address,
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
    proxy_contract.grantRole(proxy_contract.INITIATOR_ROLE(), initiator, sender=deployer)

    return proxy_contract


#
# Signing
#


def test_signing_ritual(
    project,
    chain,
    signing_coordinator,
    signing_coordinator_child,
    signing_coordinator_dispatcher,
    initiator,
    nodes,
    other_chain_signing_coordinator_child,
):
    threshold = len(nodes) // 2 + 1
    tx = signing_coordinator.initiateSigningCohort(
        chain.chain_id, initiator, nodes, threshold, DURATION, sender=initiator
    )

    signing_cohort_id = 0
    events = [event for event in tx.events if event.event_name == "InitiateSigningCohort"]
    assert len(events) == 1
    event = events[0]
    assert event.cohortId == signing_cohort_id
    assert event.authority == initiator
    assert event.chainId == chain.chain_id
    assert event.participants == [n.address for n in nodes]

    signing_cohort_struct = signing_coordinator.signingCohorts(signing_cohort_id)
    assert signing_cohort_struct["initiator"] == initiator
    init, end = signing_cohort_struct[1], signing_cohort_struct["endTimestamp"]
    assert end - init == DURATION
    assert signing_cohort_struct["authority"] == initiator
    assert signing_cohort_struct["totalSignatures"] == 0

    assert signing_cohort_struct["numSigners"] == len(nodes)
    assert signing_cohort_struct["threshold"] == threshold

    assert signing_coordinator.getChains(signing_cohort_id) == [chain.chain_id]

    for n in nodes:
        assert signing_coordinator.isSigner(signing_cohort_id, n.address)

    assert (
        signing_coordinator.getSigningCohortState(signing_cohort_id)
        == SigningRitualState.AWAITING_SIGNATURES
    )

    submitted_signatures = []
    data_hash = signing_coordinator.getSigningCohortDataHash(signing_cohort_id)
    signable_message = encode_defunct(data_hash)

    # submit signatures
    for i, node in enumerate(nodes):
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
        submitted_signatures.append(signature)

    events = [event for event in tx.events if event.event_name == "SigningCohortDeployed"]
    assert events == [
        signing_coordinator.SigningCohortDeployed(
            cohortId=signing_cohort_id,
            chainId=chain.chain_id,
        )
    ]

    assert signing_coordinator.getSigningCohortState(signing_cohort_id) == SigningRitualState.ACTIVE
    assert signing_coordinator.isCohortActive(signing_cohort_id)

    # submit conditions
    time_condition = (
        b'{"version": "1.0.0", "condition": {"chain": 80002, "method": "blocktime", '
        b'"returnValueTest": {"comparator": ">", "value": 0}, "conditionType": "time"}}'
    )

    tx = signing_coordinator.setSigningCohortConditions(
        signing_cohort_id, chain.chain_id, time_condition, sender=initiator
    )
    events = [event for event in tx.events if event.event_name == "SigningCohortConditionsSet"]
    assert events == [
        signing_coordinator.SigningCohortConditionsSet(
            cohortId=signing_cohort_id,
            chainId=chain.chain_id,
            conditions=time_condition,
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
    expected_multisig_address = project.ThresholdSigningMultisigCloneFactory.at(
        signing_coordinator_child.signingMultisigFactory()
    ).getCloneAddress(signing_cohort_id)
    assert signing_coordinator_child.cohortMultisigs(signing_cohort_id) == expected_multisig_address

    cohort_multisig = project.ThresholdSigningMultisig.at(expected_multisig_address)
    assert cohort_multisig.getSigners() == [n.address for n in nodes]
    assert cohort_multisig.threshold() == threshold
    assert cohort_multisig.owner() == signing_coordinator_child.address

    # ensure signatures are valid for deployed cohort multisig
    # (just need something signed by signers, why not reuse the data
    #  from posting of the signature in the ritual)
    data_hash = _hash_eip191_message(signable_message)

    # signatures must be all unique (no repeats)
    repeated_signature = b"".join([submitted_signatures[0]] * threshold)
    assert (
        cohort_multisig.isValidSignature(data_hash, repeated_signature) == ERC1271_INVALID_SIGNATURE
    )

    assert (
        cohort_multisig.isValidSignature(data_hash, b"".join(submitted_signatures))
        == ERC1271_MAGIC_VALUE_BYTES
    )

    #
    # deploy multisig to another chain (cross-chain test)
    #

    # deploy multisig to another chain
    tx = signing_coordinator.deployAdditionalChainForSigningMultisig(
        OTHER_CHAIN_ID_FOR_BRIDGE, signing_cohort_id, sender=initiator
    )
    events = [event for event in tx.events if event.event_name == "SigningCohortDeployed"]
    assert events == [
        signing_coordinator.SigningCohortDeployed(
            cohortId=signing_cohort_id,
            chainId=OTHER_CHAIN_ID_FOR_BRIDGE,
        )
    ]
    # new chain added
    assert signing_coordinator.getChains(signing_cohort_id) == [
        chain.chain_id,
        OTHER_CHAIN_ID_FOR_BRIDGE,
    ]

    tx = signing_coordinator.setSigningCohortConditions(
        signing_cohort_id, OTHER_CHAIN_ID_FOR_BRIDGE, time_condition, sender=initiator
    )
    events = [event for event in tx.events if event.event_name == "SigningCohortConditionsSet"]
    assert events == [
        signing_coordinator.SigningCohortConditionsSet(
            cohortId=signing_cohort_id,
            chainId=OTHER_CHAIN_ID_FOR_BRIDGE,
            conditions=time_condition,
        )
    ]
    assert (
        signing_coordinator.getCondition(signing_cohort_id, OTHER_CHAIN_ID_FOR_BRIDGE)
        == time_condition
    )

    other_chain_expected_multisig_address = project.ThresholdSigningMultisigCloneFactory.at(
        other_chain_signing_coordinator_child.signingMultisigFactory()
    ).getCloneAddress(signing_cohort_id)
    assert (
        other_chain_signing_coordinator_child.cohortMultisigs(signing_cohort_id)
        == other_chain_expected_multisig_address
    )
