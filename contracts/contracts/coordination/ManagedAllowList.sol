// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./IEncryptionAuthorizer.sol";
import "./Coordinator.sol";

contract ManagedAllowList is IEncryptionAuthorizer {
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    Coordinator public immutable coordinator;

    mapping(address => bool) public administrators;
    mapping(address => uint256) public administratorCaps;
    mapping(bytes32 => bool) internal authorizations;

    event AdministratorAdded(address indexed admin);
    event AdministratorRemoved(address indexed admin);
    event EncryptorAdded(uint32 indexed ritualId, address indexed encryptor);
    event EncryptorRemoved(uint32 indexed ritualId, address indexed encryptor);

    constructor(Coordinator _coordinator) {
        require(address(_coordinator) != address(0), "Coordinator cannot be zero address");
        require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;
    }

    modifier onlyAuthority(uint32 ritualId) {
        require(coordinator.getAuthority(ritualId) == msg.sender, "Only ritual authority is permitted");
        _;
    }

    modifier onlyAdministrator() {
        require(administrators[msg.sender], "Only administrator is permitted");
        _;
    }

    function addAdministrator(uint32 ritualId, address admin) external onlyAuthority(ritualId) {
        administrators[admin] = true;
        emit AdministratorAdded(admin);
    }

    function removeAdministrator(uint32 ritualId, address admin) external onlyAuthority(ritualId) {
        administrators[admin] = false;
        emit AdministratorRemoved(admin);
    }

    function setAdministratorCap(uint32 ritualId, address admin, uint256 cap) external onlyAuthority(ritualId) {
        administratorCaps[admin] = cap;
    }

    function addEncryptor(uint32 ritualId, address encryptor) external onlyAdministrator {
        require(administratorCaps[msg.sender] > 0, "Administrator cap reached");
        authorizations[keccak256(abi.encodePacked(ritualId, encryptor))] = true;
        administratorCaps[msg.sender]--;
        emit EncryptorAdded(ritualId, encryptor);
    }

    function removeEncryptor(uint32 ritualId, address encryptor) external onlyAdministrator {
        authorizations[keccak256(abi.encodePacked(ritualId, encryptor))] = false;
        administratorCaps[msg.sender]++;
        emit EncryptorRemoved(ritualId, encryptor);
    }

    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) external view override returns (bool) {
        bytes32 digest = keccak256(ciphertextHeader);
        address recoveredAddress = digest.toEthSignedMessageHash().recover(evidence);
        return authorizations[keccak256(abi.encodePacked(ritualId, recoveredAddress))];
    }
}
