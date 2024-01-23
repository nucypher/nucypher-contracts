// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../contracts/coordination/IEncryptionAuthorizer.sol";
import "../contracts/coordination/Coordinator.sol";

contract CoordinatorForBetaProgramInitiatorMock {
    using SafeERC20 for IERC20;

    struct Ritual {
        address initiator;
        address[] providers;
        address authority;
        uint32 duration;
        IEncryptionAuthorizer accessController;
        Coordinator.RitualState state;
        uint256 ritualCost;
    }

    IERC20 public immutable currency;

    uint256 public feeRatePerSecond = 10 ** 18;
    Ritual[] public rituals;

    constructor(IERC20 _currency) {
        currency = _currency;
    }

    function setFeeRatePerSecond(uint256 _feeRatePerSecond) external {
        feeRatePerSecond = _feeRatePerSecond;
    }

    function getRitualsLength() external view returns (uint256) {
        return rituals.length;
    }

    function getRitualInitiationCost(
        address[] calldata _providers,
        uint32 _duration
    ) public view returns (uint256) {
        return feeRatePerSecond * _providers.length * _duration;
    }

    function getRitualState(uint32 _ritualId) external view returns (Coordinator.RitualState) {
        if (_ritualId > rituals.length) {
            return Coordinator.RitualState.NON_INITIATED;
        }
        return rituals[_ritualId].state;
    }

    function getProviders(uint256 _ritualId) external view returns (address[] memory) {
        Ritual storage ritual = rituals[_ritualId];
        return ritual.providers;
    }

    function setRitualState(uint32 _ritualId, Coordinator.RitualState _state) external {
        rituals[_ritualId].state = _state;
    }

    function initiateRitual(
        address[] calldata _providers,
        address _authority,
        uint32 _duration,
        IEncryptionAuthorizer accessController
    ) external returns (uint32 ritualId) {
        Ritual storage ritual = rituals.push();
        ritual.initiator = msg.sender;
        ritual.providers = _providers;
        ritual.authority = _authority;
        ritual.duration = _duration;
        ritual.accessController = accessController;
        ritual.state = Coordinator.RitualState.DKG_AWAITING_TRANSCRIPTS;

        ritual.ritualCost = getRitualInitiationCost(_providers, _duration);
        currency.safeTransferFrom(msg.sender, address(this), ritual.ritualCost);

        return uint32(rituals.length - 1);
    }

    function feeDeduction(uint256 pending, uint256) public pure returns (uint256) {
        return pending / 10;
    }

    function pendingFees(uint256 _ritualId) external view returns (uint256) {
        return rituals[_ritualId].ritualCost;
    }

    function processPendingFee(uint32 _ritualId) public returns (uint256) {
        Ritual storage ritual = rituals[_ritualId];
        uint256 refundableFee = 0;
        if (
            ritual.state == Coordinator.RitualState.DKG_TIMEOUT ||
            ritual.state == Coordinator.RitualState.DKG_INVALID
        ) {
            refundableFee = ritual.ritualCost - feeDeduction(ritual.ritualCost, 0);
            currency.safeTransfer(ritual.initiator, refundableFee);
        }
        ritual.ritualCost = 0;
        return refundableFee;
    }
}
