// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

interface IEncryptionAuthorizer {
    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence, // supporting evidence for authorization
        bytes memory ciphertextHeader // data to be signed by authorized
    ) external view returns (bool);
}
