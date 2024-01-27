import os
from enum import IntEnum

import ape
import pytest
from eth_account.messages import encode_defunct
from web3 import Web3

TIMEOUT = 1000
MAX_DKG_SIZE = 4
FEE_RATE = 42
ERC20_SUPPLY = 10**24
DURATION = 48 * 60 * 60
ONE_DAY = 24 * 60 * 60

RitualState = IntEnum(
    "RitualState",
    [
        "NON_INITIATED",
        "DKG_AWAITING_TRANSCRIPTS",
        "DKG_AWAITING_AGGREGATIONS",
        "DKG_TIMEOUT",
        "DKG_INVALID",
        "ACTIVE",
        "EXPIRED",
    ],
    start=0,
)


# This formula returns an approximated size
# To have a representative size, create transcripts with `nucypher-core`
def transcript_size(shares, threshold):
    return int(424 + 240 * (shares / 2) + 50 * (threshold))


def gen_public_key():
    return (os.urandom(32), os.urandom(32), os.urandom(32))


def access_control_error_message(address, role=None):
    role = role or b"\x00" * 32
    return f"account={address}, neededRole={role}"


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
def erc20(project, initiator):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=initiator)
    return token


@pytest.fixture()
def coordinator(project, deployer, application, erc20, initiator, oz_dependency):
    admin = deployer
    contract = project.Coordinator.deploy(
        application.address,
        erc20.address,
        FEE_RATE,
        sender=deployer,
    )

    encoded_initializer_function = contract.initialize.encode_input(TIMEOUT, MAX_DKG_SIZE, admin)
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.Coordinator.at(proxy.address)

    proxy_contract.grantRole(contract.INITIATOR_ROLE(), initiator, sender=admin)
    return proxy_contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


def test_initial_parameters(coordinator):
    assert coordinator.maxDkgSize() == MAX_DKG_SIZE
    assert coordinator.timeout() == TIMEOUT
    assert coordinator.numberOfRituals() == 0


def test_invalid_initiate_ritual(
    project, coordinator, nodes, accounts, initiator, global_allow_list
):
    with ape.reverts("Sender can't initiate ritual"):
        sender = accounts[3]
        coordinator.initiateRitual(
            nodes, sender, DURATION, global_allow_list.address, sender=sender
        )

    with ape.reverts("Invalid number of nodes"):
        coordinator.initiateRitual(
            nodes[:5] * 20, initiator, DURATION, global_allow_list.address, sender=initiator
        )

    with ape.reverts("Invalid ritual duration"):
        coordinator.initiateRitual(nodes, initiator, 0, global_allow_list.address, sender=initiator)

    with ape.reverts("Provider has not set their public key"):
        coordinator.initiateRitual(
            nodes, initiator, DURATION, global_allow_list.address, sender=initiator
        )

    for node in nodes:
        public_key = gen_public_key()
        coordinator.setProviderPublicKey(public_key, sender=node)

    with ape.reverts("Providers must be sorted"):
        coordinator.initiateRitual(
            nodes[1:] + [nodes[0]], initiator, DURATION, global_allow_list.address, sender=initiator
        )

    with ape.reverts(project.NuCypherToken.ERC20InsufficientAllowance):
        # Sender didn't approve enough tokens
        coordinator.initiateRitual(
            nodes, initiator, DURATION, global_allow_list.address, sender=initiator
        )


def initiate_ritual(coordinator, erc20, allow_logic, authority, nodes):
    for node in nodes:
        public_key = gen_public_key()
        assert not coordinator.isProviderPublicKeySet(node)
        coordinator.setProviderPublicKey(public_key, sender=node)
        assert coordinator.isProviderPublicKeySet(node)

    cost = coordinator.getRitualInitiationCost(nodes, DURATION)
    erc20.approve(coordinator.address, cost, sender=authority)
    tx = coordinator.initiateRitual(
        nodes, authority, DURATION, allow_logic.address, sender=authority
    )
    return authority, tx


def test_initiate_ritual(
    coordinator, nodes, initiator, erc20, global_allow_list, deployer, treasury
):
    authority, tx = initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    ritualID = 0
    events = coordinator.StartRitual.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["ritualId"] == ritualID
    assert event["authority"] == authority
    assert event["participants"] == tuple(n.address.lower() for n in nodes)

    assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_TRANSCRIPTS

    ritual_struct = coordinator.rituals(ritualID)
    assert ritual_struct[0] == initiator
    init, end = ritual_struct[1], ritual_struct[2]
    assert end - init == DURATION
    total_transcripts, total_aggregations = ritual_struct[3], ritual_struct[4]
    assert total_transcripts == total_aggregations == 0
    assert ritual_struct[5] == authority
    assert ritual_struct[6] == len(nodes)
    assert ritual_struct[7] == 1 + len(nodes) // 2  # threshold
    assert not ritual_struct[8]  # aggregationMismatch
    assert ritual_struct[9] == global_allow_list.address  # accessController
    assert ritual_struct[10] == (b"\x00" * 32, b"\x00" * 16)  # publicKey
    assert not ritual_struct[11]  # aggregatedTranscript

    fee = coordinator.getRitualInitiationCost(nodes, DURATION)
    assert erc20.balanceOf(coordinator) == fee
    assert coordinator.totalPendingFees() == fee
    assert coordinator.pendingFees(ritualID) == fee

    with ape.reverts(access_control_error_message(treasury.address, coordinator.TREASURY_ROLE())):
        coordinator.withdrawTokens(erc20.address, 1, sender=treasury)

    coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
    with ape.reverts("Can't withdraw pending fees"):
        coordinator.withdrawTokens(erc20.address, 1, sender=treasury)


def test_provider_public_key(coordinator, nodes):
    selected_provider = nodes[0]
    public_key = gen_public_key()

    assert not coordinator.isProviderPublicKeySet(selected_provider)
    tx = coordinator.setProviderPublicKey(public_key, sender=selected_provider)
    assert coordinator.isProviderPublicKeySet(selected_provider)

    ritual_id = coordinator.numberOfRituals()

    events = coordinator.ParticipantPublicKeySet.from_receipt(tx)
    assert len(events) == 1
    event = events[0]
    assert event["participant"] == selected_provider
    assert event["publicKey"] == public_key
    assert coordinator.getProviderPublicKey(selected_provider, ritual_id) == public_key


def test_post_transcript(coordinator, nodes, initiator, erc20, global_allow_list):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))

    for node in nodes:
        assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_TRANSCRIPTS

        tx = coordinator.postTranscript(0, transcript, sender=node)

        events = list(coordinator.TranscriptPosted.from_receipt(tx))
        assert events == [
            coordinator.TranscriptPosted(
                ritualId=0, node=node, transcriptDigest=Web3.keccak(transcript)
            )
        ]

    participants = coordinator.getParticipants(0)
    for participant in participants:
        assert not participant.aggregated
        assert not participant.decryptionRequestStaticKey

    assert coordinator.getRitualState(0) == RitualState.DKG_AWAITING_AGGREGATIONS


def test_post_transcript_but_not_part_of_ritual(
    coordinator, nodes, initiator, erc20, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    with ape.reverts("Participant not part of ritual"):
        coordinator.postTranscript(0, transcript, sender=initiator)


def test_post_transcript_but_already_posted_transcript(
    coordinator, nodes, initiator, erc20, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    coordinator.postTranscript(0, transcript, sender=nodes[0])
    with ape.reverts("Node already posted transcript"):
        coordinator.postTranscript(0, transcript, sender=nodes[0])


def test_post_transcript_but_not_waiting_for_transcripts(
    coordinator, nodes, initiator, erc20, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    with ape.reverts("Not waiting for transcripts"):
        coordinator.postTranscript(0, transcript, sender=nodes[1])


def test_get_participants(coordinator, nodes, initiator, erc20, global_allow_list):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))

    for node in nodes:
        tx = coordinator.postTranscript(0, transcript, sender=node)

    # get all participants
    participants = coordinator.getParticipants(0, 0, len(nodes), False)
    assert len(participants) == len(nodes)
    for index, participant in enumerate(participants):
        assert participant.provider == nodes[index].address
        assert participant.aggregated is False
        assert not participant.transcript

    # max is higher than available
    participants = coordinator.getParticipants(0, 0, len(nodes)*2, False)
    assert len(participants) == len(nodes)
    for index, participant in enumerate(participants):
        assert participant.provider == nodes[index].address
        assert participant.aggregated is False
        assert not participant.transcript

    # n at a time
    for n_at_a_time in [2]:
        index = 0
        while index < len(nodes):
            print(f">>>> Start Index {index}, End Index {index+n_at_a_time}")
            participants_n_at_a_time = coordinator.getParticipants(0, index, index+n_at_a_time, True)
            assert len(participants_n_at_a_time) <= n_at_a_time
            for i, participant in enumerate(participants_n_at_a_time):
                assert participant.provider == nodes[index+i].address
                assert participant.aggregated is False
                assert participant.transcript == transcript

            index += n_at_a_time

        assert index == len(nodes)


def test_post_aggregation(
    coordinator, nodes, initiator, erc20, global_allow_list, treasury, deployer
):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    ritualID = 0
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(ritualID, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        assert coordinator.getRitualState(ritualID) == RitualState.DKG_AWAITING_AGGREGATIONS
        tx = coordinator.postAggregation(
            ritualID, aggregated, dkg_public_key, decryption_request_static_keys[i], sender=node
        )

        events = coordinator.AggregationPosted.from_receipt(tx)
        assert events == [
            coordinator.AggregationPosted(
                ritualId=ritualID, node=node, aggregatedTranscriptDigest=Web3.keccak(aggregated)
            )
        ]

    participants = coordinator.getParticipants(ritualID)
    for i, participant in enumerate(participants):
        assert participant.aggregated
        assert participant.decryptionRequestStaticKey == decryption_request_static_keys[i]

    assert coordinator.getRitualState(ritualID) == RitualState.ACTIVE
    events = coordinator.EndRitual.from_receipt(tx)
    assert events == [coordinator.EndRitual(ritualId=ritualID, successful=True)]

    retrieved_public_key = coordinator.getPublicKeyFromRitualId(ritualID)
    assert retrieved_public_key == dkg_public_key
    assert coordinator.getRitualIdFromPublicKey(dkg_public_key) == ritualID

    fee = coordinator.getRitualInitiationCost(nodes, DURATION)
    assert erc20.balanceOf(coordinator) == fee
    assert coordinator.totalPendingFees() == 0
    assert coordinator.pendingFees(ritualID) == 0

    coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
    with ape.reverts("Can't withdraw pending fees"):
        coordinator.withdrawTokens(erc20.address, fee + 1, sender=treasury)
    coordinator.withdrawTokens(erc20.address, fee, sender=treasury)


def test_post_aggregation_fails(
    coordinator, nodes, initiator, erc20, global_allow_list, treasury, deployer
):
    coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
    initiator_balance_before_payment = erc20.balanceOf(initiator)

    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )
    ritualID = 0
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(ritualID, transcript, sender=node)

    aggregated = transcript  # has the same size as transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))

    # First node does their thing
    _ = coordinator.postAggregation(
        ritualID, aggregated, dkg_public_key, decryption_request_static_keys[0], sender=nodes[0]
    )

    # Second node screws up everything
    bad_aggregated = os.urandom(transcript_size(len(nodes), len(nodes)))
    tx = coordinator.postAggregation(
        ritualID, bad_aggregated, dkg_public_key, decryption_request_static_keys[1], sender=nodes[1]
    )

    assert coordinator.getRitualState(ritualID) == RitualState.DKG_INVALID
    events = coordinator.EndRitual.from_receipt(tx)
    assert events == [coordinator.EndRitual(ritualId=ritualID, successful=False)]

    # Fees are still pending
    fee = coordinator.getRitualInitiationCost(nodes, DURATION)
    assert erc20.balanceOf(coordinator) == fee
    assert coordinator.totalPendingFees() == fee
    pending_fee = coordinator.pendingFees(ritualID)
    assert pending_fee == fee
    with ape.reverts("Can't withdraw pending fees"):
        coordinator.withdrawTokens(erc20.address, 1, sender=treasury)

    # Anyone can trigger processing of pending fees

    initiator_balance_before_refund = erc20.balanceOf(initiator)
    assert initiator_balance_before_refund == initiator_balance_before_payment - fee

    coordinator.processPendingFee(ritualID, sender=treasury)

    initiator_balance_after_refund = erc20.balanceOf(initiator)
    coordinator_balance_after_refund = erc20.balanceOf(coordinator)
    refund = initiator_balance_after_refund - initiator_balance_before_refund
    assert refund == fee - coordinator.feeDeduction(pending_fee, DURATION)
    assert coordinator_balance_after_refund + refund == fee
    assert coordinator.totalPendingFees() == 0
    assert coordinator.pendingFees(ritualID) == 0
    coordinator.withdrawTokens(erc20.address, coordinator_balance_after_refund, sender=treasury)


def test_authorize_using_global_allow_list(
    coordinator, nodes, deployer, initiator, erc20, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=global_allow_list,
    )

    # This block mocks the signature of a threshold decryption request
    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=deployer.private_key)
    signature = signed_digest.signature

    # Not authorized
    assert not global_allow_list.isAuthorized(0, bytes(signature), bytes(digest))

    # Negative test cases for authorization
    with ape.reverts("Only ritual authority is permitted"):
        global_allow_list.authorize(0, [deployer.address], sender=deployer)

    with ape.reverts("Only active rituals can add authorizations"):
        global_allow_list.authorize(0, [deployer.address], sender=initiator)

    with ape.reverts("Ritual not active"):
        coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(digest))

    # Finalize ritual
    transcript = os.urandom(transcript_size(len(nodes), len(nodes)))
    for node in nodes:
        coordinator.postTranscript(0, transcript, sender=node)

    aggregated = transcript
    decryption_request_static_keys = [os.urandom(42) for _ in nodes]
    dkg_public_key = (os.urandom(32), os.urandom(16))
    for i, node in enumerate(nodes):
        coordinator.postAggregation(
            0, aggregated, dkg_public_key, decryption_request_static_keys[i], sender=node
        )

    # Actually authorize
    tx = global_allow_list.authorize(0, [deployer.address], sender=initiator)

    # Authorized
    assert global_allow_list.isAuthorized(0, bytes(signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))
    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [global_allow_list.AddressAuthorizationSet(
        ritualId=0, _address=deployer.address, isAuthorized=True
    )]

    # Deauthorize
    tx = global_allow_list.deauthorize(0, [deployer.address], sender=initiator)

    assert not global_allow_list.isAuthorized(0, bytes(signature), bytes(data))
    assert not coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))
    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [global_allow_list.AddressAuthorizationSet(
        ritualId=0, _address=deployer.address, isAuthorized=False
    )]

    # Reauthorize in batch
    addresses_to_authorize = [deployer.address, initiator.address]
    tx = global_allow_list.authorize(0, addresses_to_authorize, sender=initiator)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=initiator.private_key)
    initiator_signature = signed_digest.signature
    assert global_allow_list.isAuthorized(0, bytes(initiator_signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(initiator_signature), bytes(data))

    assert global_allow_list.isAuthorized(0, bytes(signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))

    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=True
        ),
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=initiator.address, isAuthorized=False
        ),
    ]
