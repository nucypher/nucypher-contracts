pragma solidity ^0.8.0;

interface IEncryptionAuthorizer {
    function isAuthorized(
        uint32 ritualID,
        bytes memory evidence, // signature
        bytes32 digest   // signed message hash
    ) external view returns(bool);
}
