pragma solidity ^0.8.0;
import "@openzeppelin/contracts/access/AccessControlDefaultAdminRules.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./IEncryptionAuthorizer.sol";
import "./Coordinator.sol";


contract GlobalAllowList is AccessControlDefaultAdminRules, IEncryptionAuthorizer {
    using ECDSA for bytes32;

    Coordinator public coordinator;
    mapping(uint256 => mapping(address => bool)) public authorizations;

    constructor(
        Coordinator _coordinator,
        address _admin
    ) AccessControlDefaultAdminRules(0, _admin) {
        require(address(_coordinator) != address(0), "Coordinator cannot be zero address");
        require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;
    }

    modifier onlyAuthority(uint32 ritualId) {
        require(coordinator.getAuthority(ritualId) == msg.sender,
            "Only ritual authority is permitted");
        _;
    }

    function setCoordinator(Coordinator _coordinator) public {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Only admin can set coordinator");
        coordinator = _coordinator;
    }

    function isAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes32 digest
    ) public view override returns(bool) {
        address recovered_address = digest.toEthSignedMessageHash().recover(evidence);
        return authorizations[ritualId][recovered_address];
    }

    function authorize(uint32 ritualId, address[] calldata addresses) public onlyAuthority(ritualId) {
        require(coordinator.isRitualFinalized(ritualId),
            "Only active rituals can add authorizations");
        for (uint256 i=0; i < addresses.length; i++) {
            authorizations[ritualId][addresses[i]] = true;
        }
    }

    function deauthorize(uint32 ritualId, address[] calldata addresses) public onlyAuthority(ritualId) {
        require(coordinator.isRitualFinalized(ritualId),
            "Only active rituals can add authorizations");
        for (uint256 i=0; i < addresses.length; i++) {
            authorizations[ritualId][addresses[i]] = false;
        }
    }
}