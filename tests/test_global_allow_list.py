import os
from enum import IntEnum

import ape
import pytest
from eth_account.messages import encode_defunct
from web3 import Web3

TIMEOUT = 1000
MAX_DKG_SIZE = 31
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
def coordinator(project, deployer, application, initiator, oz_dependency):
    admin = deployer
    contract = project.Coordinator.deploy(
        application.address,
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
    return proxy_contract


@pytest.fixture()
def fee_model(project, deployer, coordinator, erc20, treasury):
    contract = project.FlatRateFeeModel.deploy(
        coordinator.address, erc20.address, FEE_RATE, sender=deployer
    )
    coordinator.grantRole(coordinator.TREASURY_ROLE(), treasury, sender=deployer)
    coordinator.approveFeeModel(contract.address, sender=treasury)
    return contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator, fee_model):
    contract = project.GlobalAllowList.deploy(
        coordinator.address, fee_model.address, sender=deployer
    )
    return contract


def initiate_ritual(coordinator, fee_model, erc20, authority, nodes, allow_logic):
    for node in nodes:
        public_key = gen_public_key()
        assert not coordinator.isProviderPublicKeySet(node)
        coordinator.setProviderPublicKey(public_key, sender=node)
        assert coordinator.isProviderPublicKeySet(node)

    cost = fee_model.getRitualCost(len(nodes), DURATION)
    erc20.approve(fee_model.address, cost, sender=authority)
    tx = coordinator.initiateRitual(
        fee_model, nodes, authority, DURATION, allow_logic.address, sender=authority
    )
    return authority, tx


def test_authorize_using_global_allow_list(
    coordinator, nodes, deployer, initiator, erc20, fee_model, global_allow_list
):
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
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

    with ape.reverts("Only active rituals can set authorizations"):
        global_allow_list.authorize(0, [deployer.address], sender=initiator)

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
    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=True
        )
    ]

    # Deauthorize
    tx = global_allow_list.deauthorize(0, [deployer.address], sender=initiator)

    assert not global_allow_list.isAuthorized(0, bytes(signature), bytes(data))
    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=False
        )
    ]

    # Reauthorize in batch
    addresses_to_authorize = [deployer.address, initiator.address]
    tx = global_allow_list.authorize(0, addresses_to_authorize, sender=initiator)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=initiator.private_key)
    initiator_signature = signed_digest.signature
    assert global_allow_list.isAuthorized(0, bytes(initiator_signature), bytes(data))

    assert global_allow_list.isAuthorized(0, bytes(signature), bytes(data))

    events = global_allow_list.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=True
        ),
        # TODO was this originally supposed to True (not sure why it passed before)
        global_allow_list.AddressAuthorizationSet(
            ritualId=0, _address=initiator.address, isAuthorized=True
        ),
    ]
