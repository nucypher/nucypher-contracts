// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

interface IEncryptionAuthorizer {
    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) external view returns (bool);
}

contract OpenAccessAuthorizer is IEncryptionAuthorizer {
    function isAuthorized(
        uint32,
        bytes memory,
        bytes memory
    ) external pure override returns (bool) {
        return true;
    }
}
