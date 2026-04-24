// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../lib/LookupKey.sol";
import "./IEncryptionAuthorizer.sol";
import "./Coordinator.sol";
import "./subscription/SharedSubscription.sol";

/**
 * @title SharedAllowList
 */
contract SharedAllowList is IEncryptionAuthorizer, Initializable {
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    Coordinator public immutable coordinator;
    uint32 public constant MAX_AUTH_ACTIONS = 100;
    mapping(address authAdmin => mapping(bytes32 lookupKey => bool)) public authAdmins;
    mapping(bytes32 lookupKey => address authAdmin) internal lookupKeys;

    /**
     * @notice Emitted when an address authorization is set
     * @param authAdmin Address that authorized
     * @param ritualId The ID of the ritual
     * @param _address The address that is authorized
     * @param isAuthorized The authorization status
     */
    event AddressAuthorizationSet(
        address indexed authAdmin,
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
     * @notice Authorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     */
    function authorize(uint32 ritualId, address[] calldata addresses) external {
        setAuthorizations(ritualId, addresses, true);
    }

    /**
     * @notice Deauthorizes a list of addresses for a ritual
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be deauthorized
     */
    function deauthorize(uint32 ritualId, address[] calldata addresses) external {
        for (uint256 i = 0; i < addresses.length; i++) {
            bytes32 lookupKey = LookupKey.lookupKey(ritualId, addresses[i]);
            require(
                authAdmins[msg.sender][lookupKey],
                "Encryptor has not been previously authorized by the sender"
            );
        }
        setAuthorizations(ritualId, addresses, false);
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
        bytes32 digest = keccak256(ciphertextHeader);
        address recoveredAddress = digest.toEthSignedMessageHash().recover(evidence);

        bytes32 lookupKey = LookupKey.lookupKey(ritualId, recoveredAddress);
        address authAdmin = lookupKeys[lookupKey];

        IFeeModel feeModel = coordinator.getFeeModel(ritualId);
        SharedSubscription(address(feeModel)).beforeIsAuthorized(authAdmin, ritualId);

        return authAdmins[authAdmin][lookupKey];
    }

    function setAuthorizations(uint32 ritualId, address[] calldata addresses, bool value) internal {
        require(coordinator.isRitualActive(ritualId), "Only active rituals can set authorizations");

        require(addresses.length <= MAX_AUTH_ACTIONS, "Too many addresses");

        IFeeModel feeModel = coordinator.getFeeModel(ritualId);
        SharedSubscription(address(feeModel)).beforeSetAuthorization(
            msg.sender,
            ritualId,
            addresses,
            value
        );

        for (uint256 i = 0; i < addresses.length; i++) {
            bytes32 lookupKey = LookupKey.lookupKey(ritualId, addresses[i]);
            // prevent reusing same address
            require(authAdmins[msg.sender][lookupKey] != value, "Authorization already set");
            authAdmins[msg.sender][lookupKey] = value;
            if (value) {
                require(
                    lookupKeys[lookupKey] == address(0),
                    "Address authorized by different admin"
                );
                lookupKeys[lookupKey] = msg.sender;
            } else {
                require(
                    lookupKeys[lookupKey] == msg.sender,
                    "Address authorized by different admin"
                );
                lookupKeys[lookupKey] = address(0);
            }
            emit AddressAuthorizationSet(msg.sender, ritualId, addresses[i], value);
        }
    }
}
