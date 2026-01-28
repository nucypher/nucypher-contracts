import os

import ape
import pytest
from ape.utils import ZERO_ADDRESS
from eth_utils import to_checksum_address

NUM_SIGNERS = 5
INITIAL_THRESHOLD = 2


@pytest.fixture(scope="module")
def signers(accounts):
    _accounts = [acc.address for acc in accounts[:NUM_SIGNERS]]
    return _accounts


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer = accounts[NUM_SIGNERS + 1]
    return deployer


@pytest.fixture(scope="module")
def signing_coordinator(project, deployer):
    _signing_coordinator = project.SigningCoordinatorMock.deploy(sender=deployer)
    return _signing_coordinator


@pytest.fixture()
def signing_coordinator_dispatcher(project, oz_dependency, signing_coordinator, deployer):
    dispatcher = project.SigningCoordinatorDispatcher.deploy(
        signing_coordinator.address,
        sender=deployer,
    )
    encoded_initializer_function = dispatcher.initialize.encode_input()
    dispatcher_proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        dispatcher.address,
        deployer,
        encoded_initializer_function,
        sender=deployer,
    )
    dispatcher_proxy_contract = project.SigningCoordinatorDispatcher.at(dispatcher_proxy.address)

    signing_coordinator.setDispatcher(dispatcher_proxy_contract.address, sender=deployer)
    return dispatcher_proxy_contract


@pytest.fixture()
def signing_coordinator_child(project, deployer):
    child = project.SigningCoordinatorChildMock.deploy(
        sender=deployer,
    )
    return child


@pytest.fixture()
def l1_sender(project, deployer):
    _l1_sender = project.L1SenderMock.deploy(
        sender=deployer,
    )
    return _l1_sender


def test_dispatcher_register_unregister(
    signing_coordinator_dispatcher,
    deployer,
    chain,
):
    # register with zero address
    with ape.reverts("Invalid L1 sender"):
        # l1 sender must not be zero address
        signing_coordinator_dispatcher.register(
            12, ZERO_ADDRESS, to_checksum_address(os.urandom(20)), sender=deployer
        )

    # register
    chain_12 = 12
    l1_sender_chain_12 = to_checksum_address(os.urandom(20))
    child_chain_12 = to_checksum_address(os.urandom(20))
    signing_coordinator_dispatcher.register(
        chain_12, l1_sender_chain_12, child_chain_12, sender=deployer
    )

    chain_13 = 13
    l1_sender_chain_13 = to_checksum_address(os.urandom(20))
    child_chain_13 = to_checksum_address(os.urandom(20))
    signing_coordinator_dispatcher.register(
        chain_13, l1_sender_chain_13, child_chain_13, sender=deployer
    )

    # verify registration
    sender, child = signing_coordinator_dispatcher.dispatchMap(chain_12)
    assert sender == l1_sender_chain_12
    assert child == child_chain_12
    assert signing_coordinator_dispatcher.getSigningCoordinatorChild(chain_12) == child_chain_12

    sender, child = signing_coordinator_dispatcher.dispatchMap(chain_13)
    assert sender == l1_sender_chain_13
    assert child == child_chain_13
    assert signing_coordinator_dispatcher.getSigningCoordinatorChild(chain_13) == child_chain_13

    # unregister
    signing_coordinator_dispatcher.unregister(chain_12, sender=deployer)
    sender, child = signing_coordinator_dispatcher.dispatchMap(chain_12)
    assert sender == ZERO_ADDRESS
    assert child == ZERO_ADDRESS

    sender, child = signing_coordinator_dispatcher.dispatchMap(chain_13)
    assert sender == l1_sender_chain_13
    assert child == child_chain_13

    # overwrite registration
    new_l1_sender_chain_13 = to_checksum_address(os.urandom(20))
    new_child_chain_13 = to_checksum_address(os.urandom(20))
    signing_coordinator_dispatcher.register(
        chain_13, new_l1_sender_chain_13, new_child_chain_13, sender=deployer
    )
    sender, child = signing_coordinator_dispatcher.dispatchMap(chain_13)
    assert sender == new_l1_sender_chain_13
    assert child == new_child_chain_13

    # registering on same chain
    current_chain = chain.chain_id
    child_current_chain = to_checksum_address(os.urandom(20))
    with ape.reverts("L1 sender not needed for same chain"):
        # l1 sender must be zero address
        l1_sender_current_chain = to_checksum_address(os.urandom(20))
        signing_coordinator_dispatcher.register(
            current_chain, l1_sender_current_chain, child_current_chain, sender=deployer
        )

    signing_coordinator_dispatcher.register(
        current_chain, ZERO_ADDRESS, child_current_chain, sender=deployer
    )
    sender, child = signing_coordinator_dispatcher.dispatchMap(current_chain)
    assert sender == ZERO_ADDRESS
    assert child == child_current_chain


def test_dispatcher_dispatch(
    project,
    signing_coordinator_dispatcher,
    signing_coordinator_child,
    signing_coordinator,
    l1_sender,
    signers,
    deployer,
):
    # register signing coordinator child for chain 42
    cohort_id = 1
    chain_id = 42
    signing_coordinator_dispatcher.register(
        chain_id, l1_sender, signing_coordinator_child.address, sender=deployer
    )

    # register signing coordinator child for other chain 43 (other chain)
    other_chain_id = 43
    other_chain_signing_coordinator_child = project.SigningCoordinatorChildMock.deploy(
        sender=deployer,
    )
    other_chain_l1_sender = project.L1SenderMock.deploy(
        sender=deployer,
    )
    signing_coordinator_dispatcher.register(
        other_chain_id,
        other_chain_l1_sender,
        other_chain_signing_coordinator_child.address,
        sender=deployer,
    )

    call_data = signing_coordinator_child.deployCohortMultiSig.encode_input(
        cohort_id, signers, INITIAL_THRESHOLD
    )
    tx = signing_coordinator.callDispatch(chain_id, call_data, sender=deployer)
    assert tx.events == [signing_coordinator_child.CohortMultisigDeployed(cohort_id, ZERO_ADDRESS)]

    # call on other chain
    call_data = other_chain_signing_coordinator_child.deployCohortMultiSig.encode_input(
        cohort_id, signers, INITIAL_THRESHOLD
    )
    tx = signing_coordinator.callDispatch(other_chain_id, call_data, sender=deployer)
    assert tx.events == [
        other_chain_signing_coordinator_child.CohortMultisigDeployed(cohort_id, ZERO_ADDRESS)
    ]

    # update multisig
    new_threshold = 3
    call_data = signing_coordinator_child.updateMultiSigParameters.encode_input(
        cohort_id, signers, new_threshold, True
    )
    tx = signing_coordinator.callDispatch(chain_id, call_data, sender=deployer)
    assert tx.events == [
        signing_coordinator_child.CohortMultisigUpdated(
            cohort_id, ZERO_ADDRESS, signers, new_threshold, True
        )
    ]
