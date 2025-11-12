import os
import random

import ape
import pytest
from eth_account.messages import _hash_eip191_message, encode_defunct

from tests.conftest import ERC1271_INVALID_SIGNATURE, ERC1271_MAGIC_VALUE_BYTES

NUM_SIGNERS = 5
INITIAL_THRESHOLD = 2


@pytest.fixture(scope="module")
def initial_signers(accounts):
    _accounts = accounts[:NUM_SIGNERS]
    _accounts = sorted([acc for acc in _accounts], key=lambda x: int(x.address, 16))
    return _accounts


@pytest.fixture(scope="module")
def new_signers(accounts):
    _accounts = accounts[NUM_SIGNERS : 2 * NUM_SIGNERS]
    _accounts = sorted(_accounts, key=lambda x: int(x.address, 16))
    return _accounts


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer = accounts[2 * NUM_SIGNERS + 1]
    return deployer


@pytest.fixture()
def threshold_signing_multisig(project, deployer, initial_signers):
    multisig = project.ThresholdSigningMultisig.deploy(sender=deployer)
    multisig.initialize(
        [signer.address for signer in initial_signers],
        INITIAL_THRESHOLD,
        deployer.address,
        sender=deployer,
    )

    return multisig


def test_signing_multisig_initialization(
    threshold_signing_multisig,
    initial_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    assert set(multisig.getSigners()) == set([signer.address for signer in initial_signers])
    assert multisig.threshold() == INITIAL_THRESHOLD
    assert multisig.owner() == deployer.address


def test_signing_multisig_add_signer(
    threshold_signing_multisig,
    initial_signers,
    new_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    new_signer = new_signers[0]
    multisig.addSigner(new_signer.address, sender=deployer)

    assert new_signer.address in multisig.getSigners()
    assert multisig.isSigner(new_signer.address) is True
    assert len(multisig.getSigners()) == len(initial_signers) + 1


def test_signing_multisig_remove_signer(
    threshold_signing_multisig,
    initial_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    signer_to_remove = initial_signers[0]
    multisig.removeSigner(signer_to_remove.address, sender=deployer)

    assert signer_to_remove.address not in multisig.getSigners()
    assert multisig.isSigner(signer_to_remove.address) is False
    assert len(multisig.getSigners()) == len(initial_signers) - 1


def test_signing_multisig_set_threshold(
    threshold_signing_multisig,
    initial_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    new_threshold = INITIAL_THRESHOLD + 1
    multisig.changeThreshold(new_threshold, sender=deployer)

    assert multisig.threshold() == new_threshold


def test_signing_multisig_unauthorized_access(
    threshold_signing_multisig,
    initial_signers,
    new_signers,
):
    multisig = threshold_signing_multisig

    unauthorized_user = new_signers[0]

    with ape.reverts(f"account={unauthorized_user.address}"):
        multisig.addSigner(new_signers[1].address, sender=unauthorized_user)

    with ape.reverts(f"account={unauthorized_user.address}"):
        multisig.removeSigner(initial_signers[0].address, sender=unauthorized_user)

    with ape.reverts(f"account={unauthorized_user.address}"):
        multisig.changeThreshold(3, sender=unauthorized_user)

    with ape.reverts(f"account={unauthorized_user.address}"):
        new_signer = new_signers[0]
        multisig.replaceSigner(
            initial_signers[0].address, new_signer.address, sender=unauthorized_user
        )


def test_signing_multisig_threshold_limits(
    threshold_signing_multisig,
    initial_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    # Test setting threshold to zero
    with ape.reverts("Invalid threshold"):
        multisig.changeThreshold(0, sender=deployer)

    # Test setting threshold greater than number of signers
    with ape.reverts("Invalid threshold"):
        multisig.changeThreshold(len(initial_signers) + 1, sender=deployer)


def test_signing_multisig_replace_signer(
    threshold_signing_multisig,
    initial_signers,
    new_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    signer_to_replace = initial_signers[0]
    new_signer = new_signers[0]

    multisig.replaceSigner(signer_to_replace.address, new_signer.address, sender=deployer)

    assert signer_to_replace.address not in multisig.getSigners()
    assert multisig.isSigner(signer_to_replace.address) is False
    assert new_signer.address in multisig.getSigners()
    assert multisig.isSigner(new_signer.address) is True
    assert len(multisig.getSigners()) == len(initial_signers)


def test_signing_multisig_is_valid_signature(
    threshold_signing_multisig,
    initial_signers,
    deployer,
):
    multisig = threshold_signing_multisig

    message = b"Test message"
    signable_message = encode_defunct(primitive=message)
    data_hash = _hash_eip191_message(signable_message)

    # Simulate signatures from initial signers
    signatures = b""
    for signer in initial_signers[:INITIAL_THRESHOLD]:
        signature = signer.sign_message(signable_message).encode_rsv()
        signatures += signature

    is_valid = multisig.isValidSignature(data_hash, signatures)
    assert is_valid == ERC1271_MAGIC_VALUE_BYTES

    with ape.reverts("Invalid threshold of signatures"):
        insufficient_threshold_signatures = signatures[:-65]
        _ = multisig.isValidSignature(data_hash, insufficient_threshold_signatures)

    is_valid = multisig.isValidSignature(data_hash, os.urandom(len(signatures)))
    assert is_valid != ERC1271_MAGIC_VALUE_BYTES
    assert is_valid == ERC1271_INVALID_SIGNATURE


def test_signing_multisig_update_parameters_bulk_replacement(
    threshold_signing_multisig,
    initial_signers,
    new_signers,
    deployer,
):
    new_threshold = INITIAL_THRESHOLD + 1
    threshold_signing_multisig.updateMultiSigParameters(
        [signer.address for signer in new_signers],
        new_threshold,
        True,  # totally replace old signers
        sender=deployer,
    )

    updated_signers = set(threshold_signing_multisig.getSigners())
    assert len(updated_signers) == NUM_SIGNERS
    assert updated_signers == set([signer.address for signer in new_signers])
    assert threshold_signing_multisig.threshold() == new_threshold
    for old_signer in initial_signers:
        assert old_signer.address not in updated_signers
        assert threshold_signing_multisig.isSigner(old_signer.address) is False

    message = b"Test message"
    signable_message = encode_defunct(primitive=message)
    data_hash = _hash_eip191_message(signable_message)

    # check that old signers can no longer perform actions
    # simulate signatures from old signers
    old_signatures = b""
    for signer in initial_signers[:INITIAL_THRESHOLD]:
        signature = signer.sign_message(signable_message).encode_rsv()
        old_signatures += signature
    with ape.reverts("Invalid threshold of signatures"):
        _ = threshold_signing_multisig.isValidSignature(data_hash, old_signatures)

    # try again with updated threshold - should still fail
    old_signatures = b""
    for signer in initial_signers[:new_threshold]:
        signature = signer.sign_message(signable_message).encode_rsv()
        old_signatures += signature
    is_valid = threshold_signing_multisig.isValidSignature(data_hash, old_signatures)
    assert is_valid != ERC1271_MAGIC_VALUE_BYTES
    assert is_valid == ERC1271_INVALID_SIGNATURE

    # check the new signers can successfully sign
    # simulate signatures from new signers
    new_signatures = b""
    for signer in new_signers[:new_threshold]:
        signature = signer.sign_message(signable_message).encode_rsv()
        new_signatures += signature
    is_valid = threshold_signing_multisig.isValidSignature(data_hash, new_signatures)
    assert is_valid == ERC1271_MAGIC_VALUE_BYTES


def test_signing_multisig_update_parameters_bulk_change_no_replacement(
    threshold_signing_multisig,
    initial_signers,
    new_signers,
    deployer,
):
    new_threshold = INITIAL_THRESHOLD + 1
    threshold_signing_multisig.updateMultiSigParameters(
        [signer.address for signer in new_signers],
        new_threshold,
        False,  # don't replace, bulk add
        sender=deployer,
    )

    updated_signers = set(threshold_signing_multisig.getSigners())
    # both original and new signers are valid
    assert len(updated_signers) == NUM_SIGNERS * 2
    for signer in initial_signers:
        assert signer.address in updated_signers
        assert threshold_signing_multisig.isSigner(signer.address) is True
    for signer in new_signers:
        assert signer.address in updated_signers
        assert threshold_signing_multisig.isSigner(signer.address) is True
    assert threshold_signing_multisig.threshold() == new_threshold

    message = b"Test message"
    signable_message = encode_defunct(primitive=message)
    data_hash = _hash_eip191_message(signable_message)

    # check that original signers can still sign
    # simulate signatures from old signers
    original_signatures = b""
    for signer in initial_signers[:INITIAL_THRESHOLD]:
        signature = signer.sign_message(signable_message).encode_rsv()
        original_signatures += signature
    with ape.reverts("Invalid threshold of signatures"):
        _ = threshold_signing_multisig.isValidSignature(data_hash, original_signatures)

    # try again with updated threshold - should pass
    original_signatures = b""
    for signer in initial_signers[:new_threshold]:
        signature = signer.sign_message(signable_message).encode_rsv()
        original_signatures += signature
    is_valid = threshold_signing_multisig.isValidSignature(data_hash, original_signatures)
    assert is_valid == ERC1271_MAGIC_VALUE_BYTES

    # simulate signatures from new signers
    new_signatures = b""
    for signer in new_signers[:new_threshold]:
        signature = signer.sign_message(signable_message).encode_rsv()
        new_signatures += signature
    is_valid = threshold_signing_multisig.isValidSignature(data_hash, new_signatures)
    assert is_valid == ERC1271_MAGIC_VALUE_BYTES

    # signature mix of old and new signers still valid
    all_signers = [*initial_signers, *new_signers]
    random_signers = random.sample(all_signers, NUM_SIGNERS)
    random_signers = sorted(random_signers, key=lambda x: int(x.address, 16))
    mixed_signatures = b""
    for signer in random_signers:
        signature = signer.sign_message(signable_message).encode_rsv()
        mixed_signatures += signature
    is_valid = threshold_signing_multisig.isValidSignature(data_hash, mixed_signatures)
    assert is_valid == ERC1271_MAGIC_VALUE_BYTES
