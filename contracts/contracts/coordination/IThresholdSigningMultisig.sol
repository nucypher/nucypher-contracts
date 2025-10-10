// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

interface IThresholdSigningMultisig {
    function initialize(address[] memory, uint16, address) external;

    function updateMultiSigParameters(
        address[] calldata signers,
        uint16 threshold,
        bool clearSigners
    ) external;
}
