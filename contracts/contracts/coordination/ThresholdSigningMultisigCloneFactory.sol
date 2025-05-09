// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "./IThresholdSigningMultisig.sol";

contract ThresholdSigningMultisigCloneFactory {
    address public immutable implementation;

    event ThresholdMultisigCloneDeployed(address cloneAddress, uint256 cohortId);

    constructor(address _implementation) {
        implementation = _implementation;
    }

    function deploySigningMultisig(
        address[] memory signers,
        uint16 threshold,
        address initialOwner,
        uint256 cohortId
    ) external returns (address) {
        bytes32 saltBytes = bytes32(cohortId);
        address clone = Clones.cloneDeterministic(implementation, saltBytes);
        IThresholdSigningMultisig(clone).initialize(signers, threshold, initialOwner);
        emit ThresholdMultisigCloneDeployed(clone, cohortId);
        return clone;
    }

    function getCloneAddress(uint256 cohortId) external view returns (address) {
        return Clones.predictDeterministicAddress(implementation, bytes32(cohortId), address(this));
    }
}
