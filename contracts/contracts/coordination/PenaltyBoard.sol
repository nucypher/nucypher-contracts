// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./Periods.sol";

/**
 * @title PenaltyBoard
 * @notice Records which staking providers are penalized per period (period-oriented summary of infractions).
 *        Independent of InfractionCollector; may live on a different chain. An informer (trusted) sets
 *        the list of penalized providers for a given period.
 */
contract PenaltyBoard is Periods, AccessControl {
    bytes32 public constant INFORMER_ROLE = keccak256("INFORMER_ROLE");

    event PenalizedProvidersSet(uint256 indexed period, address[] providers);

    mapping(uint256 period => address[]) private _penalizedProvidersByPeriod;

    constructor(
        uint256 genesisTime,
        uint256 periodDuration,
        address admin
    ) Periods(genesisTime, periodDuration) {
        require(admin != address(0), "Admin required");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function getPenalizedProvidersForPeriod(
        uint256 period
    ) external view returns (address[] memory) {
        return _penalizedProvidersByPeriod[period];
    }

    /**
     * @notice Set the list of penalized staking providers for a period.
     * @param provs Staking provider addresses to record as penalized for the period.
     * @param period Period index (must be current or previous period).
     */
    function setPenalizedProvidersForPeriod(
        address[] calldata provs,
        uint256 period
    ) external onlyRole(INFORMER_ROLE) {
        uint256 current = getCurrentPeriod();
        require(
            period == current || (current > 0 && period == current - 1),
            "Invalid period"
        );

        delete _penalizedProvidersByPeriod[period];
        for (uint256 i = 0; i < provs.length; i++) {
            _penalizedProvidersByPeriod[period].push(provs[i]);
        }

        emit PenalizedProvidersSet(period, provs);
    }
}
