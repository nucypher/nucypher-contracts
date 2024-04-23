// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

library LookupKey {
    /**
     * @notice Returns the key used to lookup authorizations
     * @param ritualId The ID of the ritual
     * @param encryptor The address of the encryptor
     * @return The key used to lookup authorizations
     */
    function lookupKey(uint32 ritualId, address encryptor) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(ritualId, encryptor));
    }
}
