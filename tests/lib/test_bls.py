import ape
import os
import pytest
from hexbytes import HexBytes

G1_SIZE = 48
G2_SIZE = 48 * 2

@pytest.fixture(scope="module")
def bls(accounts, project):
    return project.BLSLibraryMock.deploy(sender=accounts[0])

def test_constants(bls):
    assert bls.G1_POINT_SIZE() == G1_SIZE
    assert bls.G2_POINT_SIZE() == G2_SIZE

def test_bytes_to_g1(bls):
    point_bytes = os.urandom(G1_SIZE)
    word0 = HexBytes(point_bytes[:32])
    word1 = HexBytes(point_bytes[32:])
    assert tuple(bls.bytesToG1Point(point_bytes)) == (word0, word1)

def test_bytes_to_g2(bls):
    point_bytes = os.urandom(G2_SIZE)
    word0 = HexBytes(point_bytes[:32])
    word1 = HexBytes(point_bytes[32:64])
    word2 = HexBytes(point_bytes[64:])
    assert bls.bytesToG2Point(point_bytes) == (word0, word1, word2)

def test_g1_to_bytes(bls):
    g1_point = (os.urandom(32), os.urandom(16))
    assert bls.g1PointToBytes(g1_point) == HexBytes(b''.join(g1_point))

def test_g2_to_bytes(bls):
    g2_point = (os.urandom(32), os.urandom(32), os.urandom(32))
    assert bls.g2PointToBytes(g2_point) == HexBytes(b''.join(g2_point))

def test_eq_g1(bls):
    g1_point = (os.urandom(32), os.urandom(16))
    assert bls.eqG1Point(g1_point, g1_point)
    assert not bls.eqG1Point(g1_point, (os.urandom(32), os.urandom(16)))
    
def test_eq_g2(bls):
    g2_point = (os.urandom(32), os.urandom(32), os.urandom(32))
    assert bls.eqG2Point(g2_point, g2_point)
    assert not bls.eqG2Point(g2_point, (os.urandom(32), os.urandom(32), os.urandom(32)))