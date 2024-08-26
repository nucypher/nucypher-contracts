// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../coordination/IEncryptionAuthorizer.sol";

contract OpenAccessAuthorizer is IEncryptionAuthorizer {
    function isAuthorized(
        uint32,
        bytes memory,
        bytes memory
    ) external pure override returns (bool) {
        return true;
    }
}
