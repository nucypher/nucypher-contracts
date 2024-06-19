// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../contracts/coordination/IEncryptionAuthorizer.sol";
import "../contracts/coordination/Coordinator.sol";
import "../contracts/coordination/IFeeModel.sol";

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
        IFeeModel feeModel;
    }

    Ritual[] public rituals;

    function getRitualsLength() external view returns (uint256) {
        return rituals.length;
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
        IFeeModel _feeModel,
        address[] calldata _providers,
        address _authority,
        uint32 _duration,
        IEncryptionAuthorizer _accessController
    ) external returns (uint32 ritualId) {
        Ritual storage ritual = rituals.push();
        ritual.initiator = msg.sender;
        ritual.providers = _providers;
        ritual.authority = _authority;
        ritual.duration = _duration;
        ritual.accessController = _accessController;
        ritual.feeModel = _feeModel;
        ritual.state = Coordinator.RitualState.DKG_AWAITING_TRANSCRIPTS;

        uint32 id = uint32(rituals.length - 1);
        _feeModel.processRitualPayment(msg.sender, id, _providers.length, _duration);

        return id;
    }

    function getInitiator(uint32 ritualId) external view returns (address) {
        return rituals[ritualId].initiator;
    }

    function getTimestamps(
        uint32 ritualId
    ) external view returns (uint32 initTimestamp, uint32 endTimestamp) {
        initTimestamp = uint32(block.timestamp);
        endTimestamp = uint32(block.timestamp + rituals[ritualId].duration);
    }
}
