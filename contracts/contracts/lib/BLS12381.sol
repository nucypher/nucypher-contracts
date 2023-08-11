// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @notice Library for dealing with BLS12-381 entities
 */
library BLS12381 {
    uint256 public constant G1_POINT_SIZE = 48;
    uint256 public constant G2_POINT_SIZE = 96;

    // G1 points require 48 bytes, so we need 2 32-byte words
    // (or more exactly, a 32-byte word and a 16-byte word)
    struct G1Point {
        bytes32 word0;
        bytes16 word1;
    }

    // G2 points require 96 bytes, so we can use exactly 3 32-byte words
    struct G2Point {
        bytes32 word0;
        bytes32 word1;
        bytes32 word2;
    }

    function bytesToG1Point(
        bytes calldata pointBytes
    ) internal pure returns (G1Point memory point) {
        require(pointBytes.length == G1_POINT_SIZE, "Wrong G1 point size");
        point.word0 = bytes32(pointBytes[:32]);
        point.word1 = bytes16(pointBytes[32:]);
    }

    function bytesToG2Point(
        bytes calldata pointBytes
    ) internal pure returns (G2Point memory point) {
        require(pointBytes.length == G2_POINT_SIZE, "Wrong G2 point size");
        point.word0 = bytes32(pointBytes[:32]);
        point.word1 = bytes32(pointBytes[32:64]);
        point.word2 = bytes32(pointBytes[64:]);
    }

    function g1PointToBytes(G1Point memory point) internal pure returns (bytes memory) {
        return bytes.concat(point.word0, point.word1);
    }

    function g2PointToBytes(G2Point memory point) internal pure returns (bytes memory) {
        return bytes.concat(point.word0, point.word1, point.word2);
    }

    function eqG1Point(G1Point memory p0, G1Point memory p1) internal pure returns (bool) {
        return p0.word0 == p1.word0 && p0.word1 == p1.word1;
    }

    function eqG2Point(G2Point memory p0, G2Point memory p1) internal pure returns (bool) {
        return p0.word0 == p1.word0 && p0.word1 == p1.word1 && p0.word2 == p1.word2;
    }
}
