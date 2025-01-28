import os

import ape
import pytest
from eth_account.messages import encode_defunct
from web3 import Web3

from tests.conftest import gen_public_key, generate_transcript

TIMEOUT = 1000
MAX_DKG_SIZE = 31
FEE_RATE = 42
ERC20_SUPPLY = 10**24
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
def erc20(project, initiator):
    token = project.TestToken.deploy(ERC20_SUPPLY, sender=initiator)
    return token


@pytest.fixture()
def coordinator(project, deployer, application, oz_dependency):
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
    coordinator.grantRole(coordinator.FEE_MODEL_MANAGER_ROLE(), treasury, sender=deployer)
    coordinator.approveFeeModel(contract.address, sender=treasury)
    return contract


@pytest.fixture()
def global_allow_list(project, deployer, coordinator):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    return contract


@pytest.fixture()
def upgradeable_global_allow_list(project, deployer, coordinator, oz_dependency):
    contract = project.GlobalAllowList.deploy(coordinator.address, sender=deployer)
    encoded_initializer_function = b""
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    proxy_contract = project.GlobalAllowList.at(proxy.address)
    return proxy_contract


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


# Using normal and upgradeable versions of global_allow_list.
# Since both are fixtures, we need a small workaround to use them as parameters.
# See https://engineeringfordatascience.com/posts/pytest_fixtures_with_parameterize/#using-requestgetfixturevalue-
@pytest.mark.parametrize(
    "allow_list_contract",
    ("global_allow_list", "upgradeable_global_allow_list"),
)
def test_authorize_using_global_allow_list(
    coordinator, nodes, deployer, initiator, erc20, fee_model, allow_list_contract, request
):
    allow_list_contract = request.getfixturevalue(allow_list_contract)
    initiate_ritual(
        coordinator=coordinator,
        fee_model=fee_model,
        erc20=erc20,
        authority=initiator,
        nodes=nodes,
        allow_logic=allow_list_contract,
    )

    # This block mocks the signature of a threshold decryption request
    w3 = Web3()
    data = os.urandom(32)
    digest = Web3.keccak(data)
    signable_message = encode_defunct(digest)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=deployer.private_key)
    signature = signed_digest.signature
    size = len(nodes)

    # Not authorized
    assert not allow_list_contract.isAuthorized(0, bytes(signature), bytes(digest))

    # Negative test cases for authorization
    with ape.reverts("Only ritual authority is permitted"):
        allow_list_contract.authorize(0, [deployer.address], sender=deployer)

    with ape.reverts("Only active rituals can set authorizations"):
        allow_list_contract.authorize(0, [deployer.address], sender=initiator)

    with ape.reverts("Ritual not active"):
        coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(digest))

    # Finalize ritual
    threshold = coordinator.getThresholdForRitualSize(size)
    transcript = generate_transcript(size, threshold)
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
    tx = allow_list_contract.authorize(0, [deployer.address], sender=initiator)

    # Authorized
    assert allow_list_contract.isAuthorized(0, bytes(signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))
    events = allow_list_contract.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        allow_list_contract.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=True
        )
    ]

    # Deauthorize
    tx = allow_list_contract.deauthorize(0, [deployer.address], sender=initiator)

    assert not allow_list_contract.isAuthorized(0, bytes(signature), bytes(data))
    assert not coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))
    events = allow_list_contract.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        allow_list_contract.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=False
        )
    ]

    # Reauthorize in batch
    addresses_to_authorize = [deployer.address, initiator.address]
    tx = allow_list_contract.authorize(0, addresses_to_authorize, sender=initiator)
    signed_digest = w3.eth.account.sign_message(signable_message, private_key=initiator.private_key)
    initiator_signature = signed_digest.signature
    assert allow_list_contract.isAuthorized(0, bytes(initiator_signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(initiator_signature), bytes(data))

    assert allow_list_contract.isAuthorized(0, bytes(signature), bytes(data))
    assert coordinator.isEncryptionAuthorized(0, bytes(signature), bytes(data))

    events = allow_list_contract.AddressAuthorizationSet.from_receipt(tx)
    assert events == [
        allow_list_contract.AddressAuthorizationSet(
            ritualId=0, _address=deployer.address, isAuthorized=True
        ),
        # TODO was this originally supposed to True (not sure why it passed before)
        allow_list_contract.AddressAuthorizationSet(
            ritualId=0, _address=initiator.address, isAuthorized=True
        ),
    ]
