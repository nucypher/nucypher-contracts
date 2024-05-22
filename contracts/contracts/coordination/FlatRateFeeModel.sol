// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./IFeeModel.sol";
import "./Coordinator.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title FlatRateFeeModel
 * @notice FlatRateFeeModel
 */
contract FlatRateFeeModel is IFeeModel, Ownable {
    using SafeERC20 for IERC20;

    IERC20 public immutable currency;
    uint256 public immutable feeRatePerSecond;
    Coordinator public immutable coordinator;

    uint256 public totalPendingFees;
    mapping(uint256 => uint256) public pendingFees;

    constructor(
        Coordinator _coordinator,
        IERC20 _currency,
        uint256 _feeRatePerSecond
    ) Ownable(msg.sender) {
        require(_feeRatePerSecond > 0, "Invalid fee rate");
        currency = _currency;
        feeRatePerSecond = _feeRatePerSecond;
        coordinator = _coordinator;
    }

    function getRitualInitiationCost(
        uint256 numberOfProviders,
        uint32 duration
    ) public view returns (uint256) {
        require(duration > 0, "Invalid ritual duration");
        require(numberOfProviders > 0, "Invalid ritual size");
        return feeRatePerSecond * numberOfProviders * duration;
    }

    // TODO: Validate if this is enough to remove griefing attacks
    function feeDeduction(uint256, uint256) public pure returns (uint256) {
        return 0;
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external override {
        require(msg.sender == address(coordinator), "Only coordinator can call process payment");
        uint256 ritualCost = getRitualInitiationCost(numberOfProviders, duration);
        require(ritualCost > 0, "Invalid ritual cost");
        totalPendingFees += ritualCost;
        pendingFees[ritualId] = ritualCost;
        currency.safeTransferFrom(initiator, address(this), ritualCost);
    }

    function processPendingFee(uint32 ritualId) public returns (uint256 refundableFee) {
        Coordinator.RitualState state = coordinator.getRitualState(ritualId);
        require(
            state == Coordinator.RitualState.DKG_TIMEOUT ||
                state == Coordinator.RitualState.DKG_INVALID ||
                state == Coordinator.RitualState.ACTIVE ||
                state == Coordinator.RitualState.EXPIRED,
            "Ritual is not ended"
        );
        uint256 pending = pendingFees[ritualId];
        require(pending > 0, "No pending fees for this ritual");

        // Finalize fees for this ritual
        totalPendingFees -= pending;
        delete pendingFees[ritualId];
        // Transfer fees back to initiator if failed
        if (
            state == Coordinator.RitualState.DKG_TIMEOUT ||
            state == Coordinator.RitualState.DKG_INVALID
        ) {
            // Refund everything minus cost of renting cohort for a day
            address initiator = coordinator.getInitiator(ritualId);
            (uint32 initTimestamp, uint32 endTimestamp) = coordinator.getTimestamps(ritualId);
            uint256 duration = endTimestamp - initTimestamp;
            refundableFee = pending - feeDeduction(pending, duration);
            currency.safeTransfer(initiator, refundableFee);
        }
        return refundableFee;
    }

    function withdrawTokens(uint256 amount) external onlyOwner {
        require(
            amount <= currency.balanceOf(address(this)) - totalPendingFees,
            "Can't withdraw pending fees"
        );
        currency.safeTransfer(msg.sender, amount);
    }

    /**
     * @dev This function is called before the setAuthorizations function
     * @param ritualId The ID of the ritual
     * @param addresses The addresses to be authorized
     * @param value The authorization status
     */
    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) external view {
        // solhint-disable-previous-line no-empty-blocks
    }
}
