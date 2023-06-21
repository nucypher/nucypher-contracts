pragma solidity ^0.8.0;

interface IAccessController {
    function isEnricoAuthorized(
        uint256 ritualID,
        bytes memory evidence,
        bytes memory ciphertextHash
    ) external view returns(bool);
}
