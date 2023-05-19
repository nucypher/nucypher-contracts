"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os

import ape
import coincurve
import pytest
import sha3
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_account.account import Account
from eth_account.messages import HexBytes, SignableMessage, encode_defunct
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_canonical_address, to_checksum_address, to_normalized_address
from nucypher_core.umbral import PublicKey, SecretKey, Signature, Signer


def canonical_address_from_umbral_key(public_key: PublicKey) -> bytes:
    pubkey_compressed_bytes = public_key.to_compressed_bytes()
    eth_pubkey = EthKeyAPI.PublicKey.from_compressed_bytes(pubkey_compressed_bytes)
    canonical_address = eth_pubkey.to_canonical_address()
    return canonical_address


def keccak_digest(*messages: bytes) -> bytes:
    """
    Accepts an iterable containing bytes and digests it returning a
    Keccak digest of 32 bytes (keccak_256).

    Although we use SHA256 in many cases, we keep keccak handy in order
    to provide compatibility with the Ethereum blockchain.

    :param bytes: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    _hash = sha3.keccak_256()
    for message in messages:
        _hash.update(bytes(message))
    digest = _hash.digest()
    return digest


def recover_address_eip_191(message: bytes, signature: bytes) -> str:
    """
    Recover checksum address from EIP-191 signature
    """
    signable_message = encode_defunct(primitive=message)
    recovery = Account.recover_message(signable_message=signable_message, signature=signature)
    recovered_address = to_checksum_address(recovery)
    return recovered_address


def verify_eip_191(address: str, message: bytes, signature: bytes) -> bool:
    """
    EIP-191 Compatible signature verification for usage with w3.eth.sign.
    """
    recovered_address = recover_address_eip_191(message=message, signature=signature)
    signature_is_valid = recovered_address == to_checksum_address(address)
    return signature_is_valid


ALGORITHM_KECCAK256 = 0
ALGORITHM_SHA256 = 1
ALGORITHM_RIPEMD160 = 2


def get_signature_recovery_value(
    message: bytes, signature: Signature, public_key: PublicKey
) -> bytes:
    """
    Obtains the recovery value of a standard ECDSA signature.

    :param message: Signed message
    :param signature: The signature from which the pubkey is recovered
    :param public_key: The public key for verifying the signature
    :param is_prehashed: True if the message is already pre-hashed.
    Default is False, and message will be hashed with SHA256
    :return: The compressed byte-serialized representation of the recovered public key
    """

    signature = signature.to_be_bytes()
    ecdsa_signature_size = 64  # two curve scalars
    if len(signature) != ecdsa_signature_size:
        raise ValueError(f"The signature size should be {ecdsa_signature_size} B.")

    for v in (0, 1):
        v_byte = bytes([v])
        recovered_pubkey = coincurve.PublicKey.from_signature_and_message(
            signature=signature + v_byte, message=message
        )
        if public_key.to_compressed_bytes() == recovered_pubkey.format(compressed=True):
            return v_byte
    else:
        raise ValueError(
            "Signature recovery failed. "
            "Either the message, the signature or the public key is not correct"
        )


def pubkey_as_address(umbral_pubkey):
    """
    Returns the public key as b'0x' + keccak(uncompressed_bytes)[-20:]
    """
    return to_normalized_address(canonical_address_from_umbral_key(umbral_pubkey).hex())


def pubkey_as_uncompressed_bytes(umbral_pubkey):
    """
    Returns the public key as uncompressed bytes (without the prefix, so 64 bytes long)
    """
    return EthKeyAPI.PublicKey.from_compressed_bytes(umbral_pubkey.to_compressed_bytes()).to_bytes()


@pytest.fixture()
def signature_verifier(project, accounts):
    contract = accounts[0].deploy(project.SignatureVerifierMock)
    return contract


def test_recover(signature_verifier):
    message = os.urandom(100)

    # Prepare message hash
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(message)
    message_hash = hash_ctx.finalize()

    # Generate Umbral key and extract "address" from the public key
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()
    signer_address = pubkey_as_address(umbral_pubkey)

    # Sign message
    signer = Signer(umbral_privkey)
    signature = signer.sign(message)

    # Get recovery id (v) before using contract
    # If we don't have recovery id while signing
    # then we should try to recover public key with different v
    # Only the correct v will match the correct public key
    v = get_signature_recovery_value(message, signature, umbral_pubkey)
    recoverable_signature = signature.to_be_bytes() + v

    # Check recovery method in the contract
    assert signer_address == to_normalized_address(
        signature_verifier.recover(message_hash, recoverable_signature)
    )

    # Also numbers 27 and 28 can be used for v
    recoverable_signature = recoverable_signature[:-1] + bytes([recoverable_signature[-1] + 27])
    assert signer_address == to_normalized_address(
        signature_verifier.recover(message_hash, recoverable_signature)
    )

    # Only number 0,1,27,28 are supported for v
    recoverable_signature = signature.to_be_bytes() + bytes([2])
    with ape.reverts():
        signature_verifier.recover(message_hash, recoverable_signature)

    # Signature must include r, s and v
    recoverable_signature = signature.to_be_bytes()
    with ape.reverts():
        signature_verifier.recover(message_hash, recoverable_signature)


def test_address(signature_verifier):
    # Generate Umbral key and extract "address" from the public key
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()
    signer_address = pubkey_as_address(umbral_pubkey)
    umbral_pubkey_bytes = pubkey_as_uncompressed_bytes(umbral_pubkey)

    # Check extracting address in library
    result_address = signature_verifier.toAddress(umbral_pubkey_bytes)
    assert signer_address == to_normalized_address(result_address)


def test_hash(signature_verifier):
    message = os.urandom(100)

    # Prepare message hash
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(message)
    message_hash = hash_ctx.finalize()

    # Verify hash function
    assert message_hash == bytes(signature_verifier.hash(message, ALGORITHM_SHA256))


def test_verify(signature_verifier):
    message = os.urandom(100)

    # Generate Umbral key
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()
    umbral_pubkey_bytes = pubkey_as_uncompressed_bytes(umbral_pubkey)

    # Sign message using SHA-256 hash
    signer = Signer(umbral_privkey)
    signature = signer.sign(message)

    # Get recovery id (v) before using contract
    v = get_signature_recovery_value(message, signature, umbral_pubkey)
    recoverable_signature = signature.to_be_bytes() + v

    # Verify signature
    assert signature_verifier.verify(
        message, recoverable_signature, umbral_pubkey_bytes, ALGORITHM_SHA256
    )

    # Verify signature using wrong key
    umbral_privkey = SecretKey.random()
    umbral_pubkey_bytes = pubkey_as_uncompressed_bytes(umbral_privkey.public_key())
    assert not signature_verifier.verify(
        message, recoverable_signature, umbral_pubkey_bytes, ALGORITHM_SHA256
    )


def test_verify_eip191(signature_verifier):
    message = os.urandom(100)

    # Generate Umbral key
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()
    umbral_pubkey_bytes = pubkey_as_uncompressed_bytes(umbral_pubkey)

    #
    # Check EIP191 signatures: Version E
    #

    # Produce EIP191 signature (version E)
    signable_message = encode_defunct(primitive=message)
    signature = Account.sign_message(
        signable_message=signable_message, private_key=umbral_privkey.to_be_bytes()
    )
    signature = bytes(signature.signature)

    # Off-chain verify, just in case
    checksum_address = to_checksum_address(canonical_address_from_umbral_key(umbral_pubkey))
    assert verify_eip_191(address=checksum_address, message=message, signature=signature)

    # Verify signature on-chain
    version_E = b"E"
    assert signature_verifier.verifyEIP191(message, signature, umbral_pubkey_bytes, version_E)

    # Of course, it'll fail if we try using version 0
    version_0 = b"\x00"
    assert not signature_verifier.verifyEIP191(message, signature, umbral_pubkey_bytes, version_0)

    # Check that the hash-based method also works independently
    hash = signature_verifier.hashEIP191(message, version_E)
    eip191_header = "\x19Ethereum Signed Message:\n" + str(len(message))
    assert bytes(hash) == keccak_digest(eip191_header.encode() + message)

    address = signature_verifier.recover(hash, signature)
    assert address == checksum_address

    #
    # Check EIP191 signatures: Version 0
    #

    # Produce EIP191 signature (version 0)
    validator = to_canonical_address(signature_verifier.address)
    signable_message = SignableMessage(
        version=HexBytes(version_0), header=HexBytes(validator), body=HexBytes(message)
    )
    signature = Account.sign_message(
        signable_message=signable_message, private_key=umbral_privkey.to_be_bytes()
    )
    signature = bytes(signature.signature)

    # Off-chain verify, just in case
    checksum_address = to_checksum_address(canonical_address_from_umbral_key(umbral_pubkey))
    assert checksum_address == Account.recover_message(
        signable_message=signable_message, signature=signature
    )

    # On chain verify signature
    assert signature_verifier.verifyEIP191(message, signature, umbral_pubkey_bytes, version_0)

    # Of course, now it fails if we try with version E
    assert not signature_verifier.verifyEIP191(message, signature, umbral_pubkey_bytes, version_E)

    # Check that the hash-based method also works independently
    hash = signature_verifier.hashEIP191(message, version_0)
    eip191_header = b"\x19\x00" + validator
    assert bytes(hash) == keccak_digest(eip191_header + message)

    address = signature_verifier.recover(hash, signature)
    assert address == checksum_address
