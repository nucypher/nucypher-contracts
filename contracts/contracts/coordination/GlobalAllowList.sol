pragma solidity ^0.8.0;
import "@openzeppelin/contracts/access/AccessControlDefaultAdminRules.sol";
import "./IRitualAuthorizer.sol";
import "./Coordinator.sol";

contract GlobalAllowList is AccessControlDefaultAdminRules, IRitualAuthorizer {

contract AllowList is AccessControlDefaultAdminRules, IRitualAuthorizer {
    Coordinator public coordinator;

    mapping(uint256 => mapping(address => bool)) public authorizations;

    constructor(
        Coordinator _coordinator,
        address _admin
    ) AccessControlDefaultAdminRules(0, _admin) {
        coordinator = _coordinator;
    }

    function setCoordinator(Coordinator _coordinator) public {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Only admin can set coordinator");
        coordinator = _coordinator;
    }

    function isAuthorized(
        uint32 ritualID,
        bytes memory evidence,
        bytes memory ciphertextHash
    ) public view override returns(bool) {
        address enricoAddress = address(uint160(bytes20(evidence)));
        return rituals[ritualID][enricoAddress];
    }

    function authorize(uint32 ritualID, address[] calldata addresses) public {
        require(coordinator.getAuthority(ritualID) == msg.sender,
            "Only ritual authority is permitted");
        require(coordinator.isRitualFinalized(ritualID),
            "Only active rituals can add authorizations");
        for (uint i=0; i<addresses.length; i++) {
            rituals[ritualID][addresses[i]] = true;
        }
    }

    function deauthorize(uint32 ritualID, address[] calldata addresses) public {
        require(coordinator.getAuthority(ritualID) == msg.sender,
            "Only ritual authority is permitted");
        require(coordinator.isRitualFinalized(ritualID),
            "Only active rituals can add authorizations");
        for (uint i=0; i<addresses.length; i++) {
            rituals[ritualID][addresses[i]] = false;
        }
    }
}