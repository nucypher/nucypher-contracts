pragma solidity ^0.8.0;

interface IRitualAuthorizer {
    function isAuthorized(
        uint256 ritualID,
        bytes memory evidence,
        bytes memory ciphertextHash
    ) external view returns(bool);
}
