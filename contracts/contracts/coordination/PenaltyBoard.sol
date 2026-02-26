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
 * @dev Gas: getAccruedBalance/withdraw cost scales with (number of periods in accrual window) and
 *      (number of penalties in range). _getPenalizedPeriodsInRange can be optimized with binary search (monotonic array).
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

    /// Number of periods a penalty affects (penalty in period k affects k..k+PENALTY_WINDOW_PERIODS inclusive).
    uint256 private constant PENALTY_WINDOW_PERIODS = 3;

    // Accrued compensation state (lazy accrual via _computeAccruedSinceLast).
    // _lastAccruedPeriodPlusOne: 0 = never accrued (start from period 0); else start next accrual at this period.
    mapping(address staker => uint256) private _accruedBalance;
    mapping(address staker => uint256) private _lastAccruedPeriodPlusOne;

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
     * @notice Returns the full list of period indices a staker was penalized in.
     */
    function getPenalizedPeriodsByStaker(
        address staker
    ) external view returns (uint256[] memory) {
        return penalizedPeriodsByStaker[staker];
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
     * @notice Accrued compensation balance for staker up to the current period.
     *         Does not modify state; accrual is persisted on withdraw.
     */
    function getAccruedBalance(address stakingProvider) external view returns (uint256) {
        if (
            fixedCompensationPerPeriod == 0 ||
            address(compensationToken) == address(0) ||
            address(tacoApplication) == address(0)
        ) {
            return 0;
        }

        uint256 current = getCurrentPeriod();
        uint256 delta = _computeAccruedSinceLast(stakingProvider, current);
        return _accruedBalance[stakingProvider] + delta;
    }

    /**
     * @notice Withdraw accrued compensation for stakingProvider; tokens sent to beneficiary.
     */
    function withdraw(address stakingProvider) external {
        require(stakingProvider != address(0), "Staking provider required");
        require(
            fixedCompensationPerPeriod > 0 &&
                address(compensationToken) != address(0) &&
                address(tacoApplication) != address(0) &&
                fundHolder != address(0),
            "Compensation disabled"
        );

        (address owner, address beneficiaryAddress) = tacoApplication.rolesOf(stakingProvider);
        require(
            msg.sender == stakingProvider ||
                msg.sender == owner ||
                msg.sender == beneficiaryAddress,
            "Unauthorized"
        );

        uint256 current = getCurrentPeriod();

        // No accrual for stakeless providers.
        if (tacoApplication.isStakeless(stakingProvider)) {
            revert("Nothing to withdraw");
        }

        uint256 delta = _computeAccruedSinceLast(stakingProvider, current);
        uint256 amount = _accruedBalance[stakingProvider] + delta;
        require(amount > 0, "Nothing to withdraw");

        _accruedBalance[stakingProvider] = 0;
        _lastAccruedPeriodPlusOne[stakingProvider] = current + 1;

        address payable beneficiary = payable(beneficiaryAddress);

        bool ok = compensationToken.transferFrom(fundHolder, beneficiary, amount);
        require(ok, "Transfer failed");
    }

    function _computeAccruedSinceLast(
        address stakingProvider,
        uint256 currentPeriod
    ) internal view returns (uint256) {
        if (
            fixedCompensationPerPeriod == 0 ||
            address(compensationToken) == address(0) ||
            address(tacoApplication) == address(0)
        ) {
            return 0;
        }

        if (tacoApplication.isStakeless(stakingProvider)) {
            return 0;
        }

        uint256 startPeriod = _lastAccruedPeriodPlusOne[stakingProvider]; // 0 = never accrued → start at 0

        if (startPeriod > currentPeriod) {
            return 0;
        }

        uint256 fromPenalties = startPeriod > PENALTY_WINDOW_PERIODS ? startPeriod - PENALTY_WINDOW_PERIODS : 0;

        uint256[] memory penaltiesInRange = _getPenalizedPeriodsInRange(
            stakingProvider,
            fromPenalties,
            currentPeriod
        );

        // No penalties affecting this window: full periods accrue.
        if (penaltiesInRange.length == 0) {
            uint256 numPeriods = currentPeriod - startPeriod + 1;
            return numPeriods * fixedCompensationPerPeriod;
        }

        // penaltiesFactor: nPenalties == 0 => 1, nPenalties > 0 => 0.
        // Implemented by checking if there exists any penalty k with P-PENALTY_WINDOW_PERIODS <= k <= P.
        uint256 accrued = 0;
        for (uint256 p = startPeriod; p <= currentPeriod; p++) {
            bool penalized = false;
            for (uint256 i = 0; i < penaltiesInRange.length; i++) {
                uint256 k = penaltiesInRange[i];
                if (k > p) {
                    continue;
                }

                if (k + PENALTY_WINDOW_PERIODS < p) {
                    continue;
                }

                penalized = true;
                break;
            }

            if (!penalized) {
                accrued += fixedCompensationPerPeriod;
            }
        }

        return accrued;
    }

    /// @dev Optimize later: array is monotonic; use binary search for fromPeriod/toPeriod to get
    ///      the inclusive index range [i, j], then copy in one pass instead of count + copy.
    function _getPenalizedPeriodsInRange(
        address stakingProvider,
        uint256 fromPeriod,
        uint256 toPeriod
    ) internal view returns (uint256[] memory) {
        uint256[] storage all = penalizedPeriodsByStaker[stakingProvider];
        uint256 len = all.length;
        if (len == 0 || fromPeriod > toPeriod) {
            return new uint256[](0);
        }

        uint256 count;
        for (uint256 i = 0; i < len; i++) {
            uint256 p = all[i];
            if (p >= fromPeriod && p <= toPeriod) {
                count++;
            }
        }

        uint256[] memory result = new uint256[](count);
        uint256 idx;
        for (uint256 i = 0; i < len; i++) {
            uint256 p = all[i];
            if (p >= fromPeriod && p <= toPeriod) {
                result[idx] = p;
                idx++;
            }
        }

        return result;
    }
}
