// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./ISigningCoordinatorChild.sol";
import "./IThresholdSigningMultisig.sol";
import "./ThresholdSigningMultisigCloneFactory.sol";

contract SigningCoordinatorChild is ISigningCoordinatorChild, Initializable, OwnableUpgradeable {
    mapping(uint32 => address) public cohortMultisigs;
    ThresholdSigningMultisigCloneFactory public immutable signingMultisigFactory;

    constructor(ThresholdSigningMultisigCloneFactory _signingMultisigFactory) {
        signingMultisigFactory = _signingMultisigFactory;
        _disableInitializers();
    }

    function initialize() public initializer {
        __Ownable_init(msg.sender);
    }

    function deployCohortMultiSig(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold
    ) external {
        require(cohortMultisigs[cohortId] == address(0), "Multisig already deployed");
        address multisig = signingMultisigFactory.deploySigningMultisig(
            signers,
            threshold,
            address(this),
            cohortId
        );
        cohortMultisigs[cohortId] = multisig;
        emit CohortMultisigDeployed(cohortId, multisig);
    }

    function updateMultiSigParameters(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold,
        bool clearSigners
    ) external {
        address multisig = cohortMultisigs[cohortId];
        require(multisig != address(0), "Multisig not deployed");
        IThresholdSigningMultisig multisigContract = IThresholdSigningMultisig(multisig);
        multisigContract.updateMultiSigParameters(signers, threshold, clearSigners);
        emit CohortMultisigUpdated(cohortId, multisig, signers, threshold, clearSigners);
    }
}
