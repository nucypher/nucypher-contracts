// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../lib/LookupKey.sol";
import "./IEncryptionAuthorizer.sol";
import "./Coordinator.sol";

/**
 * @title GlobalAllowList
 * @notice Manages a global allow list of addresses that are authorized to decrypt ciphertexts.
 */
contract GlobalAllowList is IEncryptionAuthorizer, Initializable {
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    Coordinator public immutable coordinator;

    mapping(bytes32 => bool) internal authorizations;

    mapping(uint32 => uint256) public authActions;

    uint32 public constant MAX_AUTH_ACTIONS = 100;

    /**
     * @notice Emitted when an address authorization is set
     * @param ritualId The ID of the ritual
     * @param _address The address that is authorized
     * @param isAuthorized The authorization status
     */
    event AddressAuthorizationSet(
        uint32 indexed ritualId,
        address indexed _address,
        bool isAuthorized
    );

    /**
     * @notice Sets the coordinator contract
     * @dev The coordinator contract cannot be a zero address and must have a valid number of rituals
     * @param _coordinator The address of the coordinator contract
     */
    constructor(Coordinator _coordinator) {
        require(address(_coordinator) != address(0), "Contracts cannot be zero addresses");
        require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;
        _disableInitializers();
    }

    /**
     * @notice Checks if the sender is the authority of the ritual
     * @param ritualId The ID of the ritual
     */
    modifier canSetAuthorizations(uint32 ritualId) virtual {
        require(
            coordinator.getAuthority(ritualId) == msg.sender,
            "Only ritual authority is permitted"
        );
        _;
    }

    /**
     * @notice Checks if an address is authorized for a ritual
     * @param ritualId The ID of the ritual
     * @param encryptor The address of the encryptor
     * @return The authorization status
     */
    function isAddressAuthorized(uint32 ritualId, address encryptor) public view returns (bool) {
        return authorizations[LookupKey.lookupKey(ritualId, encryptor)];
    }

    /**
     * @dev This function is called before the isAuthorized function
     * @param ritualId The ID of the ritual
     * @param evidence The evidence provided
     * @param ciphertextHeader The header of the ciphertext
     */
    function _beforeIsAuthorized(
        uint32 ritualId,
        // solhint-disable-next-line no-unused-vars
        bytes memory evidence,
        // solhint-disable-next-line no-unused-vars
        bytes memory ciphertextHeader
    ) internal view virtual {
        IFeeModel feeModel = coordinator.getFeeModel(ritualId);
        feeModel.beforeIsAuthorized(ritualId);
    }

    /**
     * @param ritualId The ID of the ritual
     * @param evidence The evidence provided
     * @param ciphertextHeader The header of the ciphertext
     * @return The authorization status
     */
    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) external view override returns (bool) {
        _beforeIsAuthorized(ritualId, evidence, ciphertextHeader);

        bytes32 digest = keccak256(ciphertextHeader);
        address recoveredAddress = digest.toEthSignedMessageHash().recover(evidence);
        return isAddressAuthorized(ritualId, recoveredAddress);
    }

    /**
     * @dev This function is called before the setAuthorizations function
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     * @param value The authorization status
     */
    function _beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) internal virtual {
        IFeeModel feeModel = coordinator.getFeeModel(ritualId);
        feeModel.beforeSetAuthorization(ritualId, addresses, value);
    }

    /**
     * @notice Authorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     */
    function authorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external virtual canSetAuthorizations(ritualId) {
        setAuthorizations(ritualId, addresses, true);
    }

    /**
     * @notice Deauthorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be deauthorized
     */
    function deauthorize(
        uint32 ritualId,
        address[] calldata addresses
    ) external virtual canSetAuthorizations(ritualId) {
        setAuthorizations(ritualId, addresses, false);
    }

    /**
     * @notice Sets the authorization status for a list of addresses for a ritual
     * @dev Only active rituals can set authorizations
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized or deauthorized
     * @param value The authorization status
     */
    function setAuthorizations(uint32 ritualId, address[] calldata addresses, bool value) internal {
        require(coordinator.isRitualActive(ritualId), "Only active rituals can set authorizations");

        require(addresses.length <= MAX_AUTH_ACTIONS, "Too many addresses");

        _beforeSetAuthorization(ritualId, addresses, value);
        for (uint256 i = 0; i < addresses.length; i++) {
            bytes32 lookupKey = LookupKey.lookupKey(ritualId, addresses[i]);
            // prevent reusing same address
            require(authorizations[lookupKey] != value, "Authorization already set");
            authorizations[lookupKey] = value;
            emit AddressAuthorizationSet(ritualId, addresses[i], value);
        }

        authActions[ritualId] += addresses.length;
    }
}
