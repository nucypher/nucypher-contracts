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

import brownie
import pytest
from nucypher_core import MessageKit
from nucypher_core.umbral import SecretKey, Signer, generate_kfrags, reencrypt


@pytest.fixture()
def deserializer(UmbralDeserializerMock, accounts):
    contract = accounts[0].deploy(UmbralDeserializerMock)
    return contract


@pytest.fixture(scope="module")
def fragments():
    delegating_privkey = SecretKey.random()
    delegating_pubkey = delegating_privkey.public_key()
    signing_privkey = SecretKey.random()
    signer = Signer(signing_privkey)
    priv_key_bob = SecretKey.random()
    pub_key_bob = priv_key_bob.public_key()
    kfrags = generate_kfrags(
        delegating_sk=delegating_privkey,
        signer=signer,
        receiving_pk=pub_key_bob,
        threshold=2,
        shares=4,
        sign_delegating_key=False,
        sign_receiving_key=False,
    )

    capsule = MessageKit(delegating_pubkey, b"unused").capsule
    cfrag = reencrypt(capsule, kfrags[0])
    return capsule, cfrag


def test_capsule(deserializer, fragments):
    # Wrong number of bytes to deserialize capsule
    with brownie.reverts():
        deserializer.toCapsule(os.urandom(97))
    with brownie.reverts():
        deserializer.toCapsule(os.urandom(99))

    # Check random capsule bytes
    capsule_bytes = os.urandom(98)
    result = deserializer.toCapsule(capsule_bytes)
    assert capsule_bytes == bytes().join(bytes(item) for item in result)

    # Check real capsule
    capsule, _cfrag = fragments
    capsule_bytes = bytes(capsule)
    result = deserializer.toCapsule(capsule_bytes)
    assert b"".join(result) == capsule_bytes


def test_cfrag(deserializer, fragments):
    # Wrong number of bytes to deserialize cfrag
    with brownie.reverts():
        deserializer.toCapsuleFrag(os.urandom(358))

    # Check random cfrag bytes
    cfrag_bytes = os.urandom(131)
    proof_bytes = os.urandom(228)
    full_cfrag_bytes = cfrag_bytes + proof_bytes
    result = deserializer.toCapsuleFrag(full_cfrag_bytes)
    assert cfrag_bytes == bytes().join(result)
    result = deserializer.toCorrectnessProofFromCapsuleFrag(full_cfrag_bytes)
    assert proof_bytes == bytes().join(result)

    # Check real cfrag
    _capsule, cfrag = fragments
    cfrag_bytes = bytes(cfrag)
    result_frag = deserializer.toCapsuleFrag(cfrag_bytes)
    result_proof = deserializer.toCorrectnessProofFromCapsuleFrag(cfrag_bytes)
    assert cfrag_bytes == b"".join(result_frag) + b"".join(result_proof)


# TODO: Missing test for precomputed_data
