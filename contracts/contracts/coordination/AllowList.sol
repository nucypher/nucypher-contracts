pragma solidity ^0.8.0;
import "@openzeppelin/contracts/access/AccessControl.sol";
import "./IAccessController.sol";
import "./Coordinator.sol";

contract AllowList is AccessControl, IAccessController {
    Coordinator public coordinator;

    // mapp
    mapping(uint256 => mapping(address => bool)) public rituals;

    constructor(Coordinator _coordinator) {
        coordinator = _coordinator;
    }

    function bytesToAddress(bytes memory bys) private pure returns (address addr) {
        assembly {
            addr := mload(add(bys, 20))
        }
    }

    function isEnricoAuthorized(
        uint256 ritualID,
        bytes memory evidence,
        bytes memory ciphertextHash
    ) public view override returns(bool) {
        enricoAddress = address(uint160(bytes20(evidence)));
        return rituals[ritualID][enricoAddress];
    }

    function authorize(uint256 ritualID, address[] calldata addresses) public {
        require(coordinator.rituals(ritualId).authority == msg.sender,
            "Only ritual authority is permitted");
        require(coordinator.getRitualStatus(ritualId) == RitualStatus.ACTIVE,
            "Only active rituals can add authorizations");
        for (uint i=0; i<addresses.length; i++) {
            rituals[ritualID][addresses[i]] = true;
        }
    }

    function deauthorize(uint256 ritualID, address[] calldata addresses) public {
        require(coordinator.rituals(ritualId).authority == msg.sender,
            "Only ritual authority is permitted");
        require(coordinator.getRitualStatus(ritualId) == RitualStatus.ACTIVE,
            "Only active rituals can add authorizations");
        for (uint i=0; i<addresses.length; i++) {
            rituals[ritualID][addresses[i]] = false;
        }
    }
}