pragma solidity ^0.8.0;

interface IRitualAuthorizer {
    function isAuthorized(
        uint32 ritualID,
        bytes memory evidence, // signature
        bytes memory digest   // signed message hash
    ) external view returns(bool);
}
