// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
 * @title ITACoApplicationForPenaltyBoard
 * @notice Minimal view interface that PenaltyBoard (with compensation) needs from TACoApplication.
 *        Used for withdrawal auth (owner, beneficiary), payout address (beneficiary), and stakeless check.
 */
interface ITACoApplicationForPenaltyBoard {
    /**
     * @notice Returns beneficiary for a staking provider (tokens are sent here on withdraw).
     *         Assumed never zero for a registered staking provider.
     */
    function getBeneficiary(address stakingProvider) external view returns (address payable beneficiary);

    /**
     * @notice Returns owner and beneficiary for a staking provider.
     *         Withdraw(stakingProvider) may be called by stakingProvider, owner, or beneficiary.
     *         If TACoApplication does not expose this, PenaltyBoard may depend on IStaking.rolesOf instead.
     */
    function getRoles(address stakingProvider) external view returns (address owner, address beneficiary);

    /**
     * @notice Returns true if the staking provider is stakeless (compensation = 0).
     *         If not present on TACoApplication, implementation may return false.
     */
    function isStakeless(address stakingProvider) external view returns (bool);
}
