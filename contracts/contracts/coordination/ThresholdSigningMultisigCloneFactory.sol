// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "./IThresholdSigningMultisig.sol";

contract ThresholdSigningMultisigCloneFactory {
    address public immutable implementation;

    event ThresholdMultisigCloneDeployed(address cloneAddress, uint256 _cohortId);

    constructor(address _implementation) {
        implementation = _implementation;
    }

    function deploySigningMultisig(
        address[] memory _signers,
        uint16 _threshold,
        address _initialOwner,
        uint256 _cohortId
    ) external returns (address) {
        bytes32 saltBytes = bytes32(_cohortId);
        address clone = Clones.cloneDeterministic(implementation, saltBytes);
        IThresholdSigningMultisig(clone).initialize(_signers, _threshold, _initialOwner);
        emit ThresholdMultisigCloneDeployed(clone, _cohortId);
        return clone;
    }

    function getCloneAddress(uint256 _cohortId) external view returns (address) {
        return
            Clones.predictDeterministicAddress(implementation, bytes32(_cohortId), address(this));
    }
}
