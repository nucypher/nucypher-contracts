// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./Periods.sol";
import "./ITACoApplicationForPenaltyBoard.sol";

/**
 * @title PenaltyBoard
 * @notice Records which staking providers are penalized per period (period-oriented summary of infractions).
 *        Independent of InfractionCollector; may live on a different chain. An informer (trusted) sets
 *        the list of penalized providers for a given period.
 *        With compensation enabled (7-arg constructor): also maintains staker-centric penalty list,
 *        accrued compensation balance, and withdraw to beneficiary.
 */
contract PenaltyBoard is Periods, AccessControl {
    bytes32 public constant INFORMER_ROLE = keccak256("INFORMER_ROLE");

    event PenalizedProvidersSet(uint256 indexed period, address[] providers);

    // Compensation (optional: when tacoApplication != address(0))
    ITACoApplicationForPenaltyBoard public immutable tacoApplication;
    IERC20 public immutable compensationToken;
    address public immutable fundHolder;
    uint256 public immutable fixedCompensationPerPeriod;

    /**
     * @notice Staker-centric penalty storage: list of period indices this staker was penalized in
     *         (monotonic append; periods are kept as uint256).
     */
    mapping(address staker => uint256[]) public penalizedPeriodsByStaker;

    /**
     * @notice Returns the full list of period indices a staker was penalized in.
     */
    function getPenalizedPeriodsByStaker(
        address staker
    ) external view returns (uint256[] memory) {
        return penalizedPeriodsByStaker[staker];
    }

    /**
     * @param genesisTime Start of period 0.
     * @param periodDuration Duration of one period in seconds.
     * @param admin Default admin.
     * @param _tacoApplication TACo (or mock) for beneficiary/owner/stakeless. Pass address(0) to disable compensation.
     * @param _token Compensation token. Pass address(0) when compensation disabled.
     * @param _fixedCompensationPerPeriod Fixed amount per period (0 when disabled).
     * @param _fundHolder Holder of tokens for payouts. Pass address(0) when compensation disabled.
     */
    constructor(
        uint256 genesisTime,
        uint256 periodDuration,
        address admin,
        address _tacoApplication,
        address _token,
        uint256 _fixedCompensationPerPeriod,
        address _fundHolder
    ) Periods(genesisTime, periodDuration) {
        require(admin != address(0), "Admin required");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        tacoApplication = ITACoApplicationForPenaltyBoard(_tacoApplication);
        compensationToken = IERC20(_token);
        fundHolder = _fundHolder;
        fixedCompensationPerPeriod = _fixedCompensationPerPeriod;
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
        require(period == current || (current > 0 && period == current - 1), "Invalid period");

        for (uint256 i = 0; i < provs.length; i++) {
            penalizedPeriodsByStaker[provs[i]].push(period);
        }

        emit PenalizedProvidersSet(period, provs);
    }

    /**
     * @notice Accrued compensation balance for staker (stub: 0 until C3).
     */
    function getAccruedBalance(address /* staker */) external pure returns (uint256) {
        return 0;
    }

    /**
     * @notice Withdraw accrued compensation for stakingProvider; tokens sent to beneficiary. Stub: reverts until C3.
     */
    function withdraw(address /* stakingProvider */) external pure {
        revert("Not implemented");
    }
}
