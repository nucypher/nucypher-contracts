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

import itertools

import pytest
from web3 import Web3


@pytest.fixture(scope="module")
def snapshot(accounts, project):
    contract = accounts[0].deploy(project.SnapshotMock)
    return contract


timestamps = (0x00000001, 0x00001000, 0xFF000000, 0xFFFF0001)

values = (
    0x000000000000000000000000,
    0x000000000001000000000001,
    0xFF0000000000000000000000,
    0xFFFF00000000000000000001,
)


@pytest.mark.parametrize("block_number, value", itertools.product(timestamps, values))
def test_snapshot(accounts, snapshot, block_number, value):

    # Testing basic encoding and decoding of snapshots
    def encode(_time, _value):
        return snapshot.encodeSnapshot(_time, _value)

    def decode(_snapshot):
        return snapshot.decodeSnapshot(_snapshot)

    encoded_snapshot = encode(block_number, value)
    assert decode(encoded_snapshot) == (block_number, value)
    expected_encoded_snapshot_as_bytes = block_number.to_bytes(4, "big") + value.to_bytes(12, "big")
    assert Web3.to_bytes(encoded_snapshot).rjust(16, b"\x00") == expected_encoded_snapshot_as_bytes

    # Testing adding new snapshots
    account = accounts[0]

    data = [(block_number + i * 10, value + i) for i in range(10)]
    for i, (block_i, value_i) in enumerate(data):
        snapshot.addSnapshot(block_i, value_i, sender=account)

        assert snapshot.length() == i + 1
        assert snapshot.call_view_method("history", i) == encode(block_i, value_i)
        assert snapshot.lastSnapshot() == (block_i, value_i)

    # Testing getValueAt: simple case, when asking for the exact block number that was recorded
    for i, (block_i, value_i) in enumerate(data):
        assert snapshot.getValueAt(block_i) == value_i
        assert snapshot.call_view_method("history", i) == encode(block_i, value_i)

    # Testing getValueAt: general case, when retrieving block numbers in-between snapshots
    # Special cases are before first snapshot (where value should be 0) and after the last one
    prior_value = 0
    for block_i, value_i in data:
        assert snapshot.getValueAt(block_i - 1) == prior_value
        prior_value = value_i

    last_block, last_value = snapshot.lastSnapshot()
    assert snapshot.getValueAt(last_block + 100) == last_value

    # Clear history for next test
    snapshot.deleteHistory(sender=account)
