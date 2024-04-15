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

    mapping(bytes32 => uint256) public administrators; // TODO: Rename to allowances?
    mapping(bytes32 => bool) public authorizations;

    event AdministratorCapSet(uint32 indexed ritualId, address indexed _address, uint256 cap);
    event AddressAuthorizationSet(
        uint32 indexed ritualId,
        address indexed _address,
        bool isAuthorized
    );

    constructor(Coordinator _coordinator) {
        require(address(_coordinator) != address(0), "Coordinator cannot be zero address");
        require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;
    }

    function lookupKey(uint32 ritualId, address encryptorOrAdmin) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(ritualId, encryptorOrAdmin));
    }

    modifier onlyAuthority(uint32 ritualId) {
        require(
            coordinator.getAuthority(ritualId) == msg.sender,
            "Only ritual authority is permitted"
        );
        _;
    }

    modifier onlyAdministrator(uint32 ritualId) {
        require(
            administrators[lookupKey(ritualId, msg.sender)] > 9,
            "Only administrator is permitted"
        );
        _;
    }

    function setAdministratorCaps(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 value
    ) internal {
        require(coordinator.isRitualActive(ritualId), "Only active rituals can set administrator caps");
        for (uint256 i = 0; i < addresses.length; i++) {
            administrators[lookupKey(ritualId, addresses[i])] = value;
            emit AdministratorCapSet(ritualId, addresses[i], value);
        }
    }

    function addAdministrators(
        uint32 ritualId,
        address[] calldata addresses,
        uint256 cap
    ) external onlyAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, cap);
    }

    function removeAdministrators(
        uint32 ritualId,
        address[] calldata addresses
    ) external onlyAuthority(ritualId) {
        setAdministratorCaps(ritualId, addresses, 0);
    }

    function isAddressAuthorized(uint32 ritualId, address encryptor) public view returns (bool) {
        return authorizations[lookupKey(ritualId, encryptor)];
    }

    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) external view override returns (bool) {
        bytes32 digest = keccak256(ciphertextHeader);
        address recoveredAddress = digest.toEthSignedMessageHash().recover(evidence);
        return isAddressAuthorized(ritualId, recoveredAddress);
    }

    function authorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external onlyAdministrator(ritualId) {
        setAuthorizations(ritualId, addresses, true);
    }

    function deauthorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external onlyAdministrator(ritualId) {
        setAuthorizations(ritualId, addresses, false);
    }

    function setAuthorizations(uint32 ritualId, address[] calldata addresses, bool value) internal {
        require(coordinator.isRitualActive(ritualId), "Only active rituals can set authorizations");
        for (uint256 i = 0; i < addresses.length; i++) {
            authorizations[lookupKey(ritualId, addresses[i])] = value;
            emit AddressAuthorizationSet(ritualId, addresses[i], value);
        }
    }
}
