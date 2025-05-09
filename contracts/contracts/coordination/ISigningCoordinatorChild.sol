// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title ISigningCoordinatorChild
 * @notice Interface for x-chain interactions from SigningCoordinator to Child
 */
interface ISigningCoordinatorChild {
    event CohortMultisigDeployed(uint32 indexed cohortId, address multisig);
    event CohortMultisigUpdated(
        uint32 indexed cohortId,
        address multisig,
        address[] signers,
        uint16 threshold,
        bool clearSigners
    );

    function deployCohortMultiSig(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold
    ) external;

    function updateMultiSigParameters(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold,
        bool clearSigners
    ) external;
}
