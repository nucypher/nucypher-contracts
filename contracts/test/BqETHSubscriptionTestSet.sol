// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../contracts/coordination/IEncryptionAuthorizer.sol";
import "../contracts/coordination/Coordinator.sol";
import "../contracts/coordination/IFeeModel.sol";

contract CoordinatorForBqETHSubscriptionMock {
    struct Ritual {
        uint32 endTimestamp;
        IEncryptionAuthorizer accessController;
        Coordinator.RitualState state;
    }

    IFeeModel public feeModel;

    mapping(uint32 => Ritual) public rituals;

    function setFeeModel(IFeeModel _feeModel) external {
        feeModel = _feeModel;
    }

    function processRitualExtending(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external {
        feeModel.processRitualExtending(initiator, ritualId, numberOfProviders, duration);
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external {
        feeModel.processRitualPayment(initiator, ritualId, numberOfProviders, duration);
    }

    function setRitual(
        uint32 _ritualId,
        Coordinator.RitualState _state,
        uint32 _endTimestamp,
        IEncryptionAuthorizer _accessController
    ) external {
        Ritual storage ritual = rituals[_ritualId];
        ritual.state = _state;
        ritual.endTimestamp = _endTimestamp;
        ritual.accessController = _accessController;
    }

    function getAccessController(uint32 _ritualId) external view returns (IEncryptionAuthorizer) {
        return rituals[_ritualId].accessController;
    }

    function getRitualState(uint32 _ritualId) external view returns (Coordinator.RitualState) {
        return rituals[_ritualId].state;
    }

    function getTimestamps(
        uint32 _ritualId
    ) external view returns (uint32 initTimestamp, uint32 endTimestamp) {
        initTimestamp = 0;
        endTimestamp = rituals[_ritualId].endTimestamp;
    }

    function numberOfRituals() external pure returns (uint256) {
        return 1;
    }

    function getAuthority(uint32) external view returns (address) {
        // solhint-disable-next-line avoid-tx-origin
        return tx.origin;
    }

    function isRitualActive(uint32) external view returns (bool) {
        return true;
    }
}
