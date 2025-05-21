// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./ISigningCoordinatorChild.sol";
import "./IThresholdSigningMultisig.sol";
import "./ThresholdSigningMultisigCloneFactory.sol";

contract SigningCoordinatorChild is ISigningCoordinatorChild, Initializable, OwnableUpgradeable {
    mapping(uint32 => address) public cohortMultisigs;
    ThresholdSigningMultisigCloneFactory public signingMultisigFactory;
    address public allowedCaller;

    event MultisigFactoryUpdated(address oldFactory, address newFactory);
    event AllowedCallerUpdated(address oldCaller, address newCaller);

    constructor() {
        _disableInitializers();
    }

    function initialize(
        ThresholdSigningMultisigCloneFactory _signingMultisigFactory,
        address _allowedCaller
    ) public initializer {
        require(address(_signingMultisigFactory).code.length > 0, "Factory must be contract");
        signingMultisigFactory = _signingMultisigFactory;
        // L2 receiver on L2; Dispatcher on L1
        allowedCaller = _allowedCaller;
        __Ownable_init(msg.sender);
    }

    function setMultisigFactory(
        ThresholdSigningMultisigCloneFactory multisigFactory
    ) external onlyOwner {
        require(address(multisigFactory).code.length > 0, "Factory must be contract");
        emit MultisigFactoryUpdated(address(signingMultisigFactory), address(multisigFactory));
        signingMultisigFactory = multisigFactory;
    }

    function setAllowedCaller(address _allowedCaller) external onlyOwner {
        require(_allowedCaller != address(0), "Invalid address");
        emit AllowedCallerUpdated(allowedCaller, _allowedCaller);
        // L2 receiver on L2; Dispatcher on L1
        allowedCaller = _allowedCaller;
    }

    function deployCohortMultiSig(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold
    ) external {
        require(allowedCaller == msg.sender, "Unauthorized caller");
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
        require(allowedCaller == msg.sender, "Unauthorized caller");
        address multisig = cohortMultisigs[cohortId];
        require(multisig != address(0), "Multisig not deployed");
        IThresholdSigningMultisig multisigContract = IThresholdSigningMultisig(multisig);
        multisigContract.updateMultiSigParameters(signers, threshold, clearSigners);
        emit CohortMultisigUpdated(cohortId, multisig, signers, threshold, clearSigners);
    }
}
