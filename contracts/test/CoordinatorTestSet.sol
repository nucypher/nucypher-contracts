// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../threshold/ITACoChildApplication.sol";
import "../contracts/coordination/Coordinator.sol";

/**
 * @notice Contract for testing Coordinator contract
 */
contract ChildApplicationForCoordinatorMock is ITACoChildApplication {
    uint96 public minimumAuthorization = 0;

    mapping(address => uint96) public authorizedStake;
    mapping(address => address) public stakingProviderToOperator;
    mapping(address => address) public operatorToStakingProvider;
    mapping(address => bool) public confirmations;

    function updateOperator(address _stakingProvider, address _operator) external {
        address oldOperator = stakingProviderToOperator[_stakingProvider];
        operatorToStakingProvider[oldOperator] = address(0);
        stakingProviderToOperator[_stakingProvider] = _operator;
        operatorToStakingProvider[_operator] = _stakingProvider;
    }

    function updateAuthorization(address _stakingProvider, uint96 _amount) external {
        authorizedStake[_stakingProvider] = _amount;
    }

    function confirmOperatorAddress(address _operator) external {
        confirmations[_operator] = true;
    }

    // solhint-disable-next-line no-empty-blocks
    function penalize(address _stakingProvider) external {}
}

contract ExtendedCoordinator is Coordinator {
    constructor(ITACoChildApplication _application) Coordinator(_application) {}

    function initiateOldRitual(
        IFeeModel feeModel,
        address[] calldata providers,
        address authority,
        uint32 duration,
        IEncryptionAuthorizer accessController
    ) external returns (uint32) {
        uint16 length = uint16(providers.length);

        uint32 id = uint32(ritualsStub.length);
        Ritual storage ritual = ritualsStub.push();
        ritual.initiator = msg.sender;
        ritual.authority = authority;
        ritual.dkgSize = length;
        ritual.threshold = getThresholdForRitualSize(length);
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.endTimestamp = ritual.initTimestamp + duration;
        ritual.accessController = accessController;
        ritual.feeModel = feeModel;

        address previous = address(0);
        for (uint256 i = 0; i < length; i++) {
            Participant storage newParticipant = ritual.participant.push();
            address current = providers[i];
            newParticipant.provider = current;
            previous = current;
        }
        return id;
    }
}
