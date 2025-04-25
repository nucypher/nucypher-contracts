import os
from enum import IntEnum

import pytest
from ape import project
from hexbytes import HexBytes

# Common constants
G1_SIZE = 48
G2_SIZE = 48 * 2
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

ERC1271_MAGIC_VALUE_BYTES = bytes(HexBytes("0x1626ba7e"))
ERC1271_INVALID_SIGNATURE = bytes(HexBytes("0xffffffff"))


SigningRitualState = IntEnum(
    "SigningRitualState",
    ["NON_INITIATED", "AWAITING_SIGNATURES", "TIMEOUT", "ACTIVE", "EXPIRED"],
    start=0,
)


# Utility functions
def transcript_size(shares, threshold):
    return 40 + (1 + shares) * G2_SIZE + threshold * G1_SIZE


def generate_transcript(shares, threshold):
    return os.urandom(transcript_size(shares, threshold))


def gen_public_key():
    return (os.urandom(32), os.urandom(32), os.urandom(32))


def access_control_error_message(address, role=None):
    role = role or b"\x00" * 32
    return f"account={address}, neededRole={role}"


# Fixtures
@pytest.fixture(scope="session")
def oz_dependency():
    return project.dependencies["openzeppelin"]["5.0.0"]


@pytest.fixture
def creator(accounts):
    return accounts[0]


@pytest.fixture
def account1(accounts):
    return accounts[1]


@pytest.fixture
def account2(accounts):
    return accounts[2]
