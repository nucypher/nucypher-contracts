// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/coordination/ITACoApplicationForPenaltyBoard.sol";

/**
 * @notice Mock TACoApplication for PenaltyBoard compensation tests.
 *         Allows tests to set owner, beneficiary, and isStakeless per staking provider.
 */
contract MockTACoForPenaltyBoard is ITACoApplicationForPenaltyBoard {
    struct StakerRoles {
        address owner;
        address payable beneficiary;
        bool isStakeless;
    }

    mapping(address stakingProvider => StakerRoles) private _roles;

    function setRoles(
        address stakingProvider,
        address owner,
        address payable beneficiary,
        bool isStakeless
    ) external {
        _roles[stakingProvider] = StakerRoles({
            owner: owner,
            beneficiary: beneficiary,
            isStakeless: isStakeless
        });
    }

    function getBeneficiary(address stakingProvider) external view returns (address payable) {
        return _roles[stakingProvider].beneficiary;
    }

    function getRoles(address stakingProvider) external view returns (address owner, address beneficiary) {
        StakerRoles storage r = _roles[stakingProvider];
        return (r.owner, r.beneficiary);
    }

    function isStakeless(address stakingProvider) external view returns (bool) {
        return _roles[stakingProvider].isStakeless;
    }
}
