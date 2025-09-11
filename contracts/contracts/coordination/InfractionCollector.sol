// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./Coordinator.sol";
import "../../threshold/ITACoChildApplication.sol";

contract InfractionCollector is OwnableUpgradeable {
    event InfractionReported(
        uint32 indexed ritualId,
        address indexed stakingProvider,
        InfractionType infractionType
    );
    // infraction types
    enum InfractionType {
        MISSING_TRANSCRIPT
    }
    Coordinator public immutable coordinator;
    // Reference to the TACoChildApplication contract
    ITACoChildApplication public immutable tacoChildApplication;
    // Mapping to keep track of reported infractions
    mapping(uint32 ritualId => mapping(address stakingProvider => mapping(InfractionType => uint256)))
        public infractionsForRitual;

    constructor(Coordinator _coordinator) {
        require(address(_coordinator) != address(0), "Contracts must be specified");
        coordinator = _coordinator;
        tacoChildApplication = coordinator.application();
        _disableInitializers();
    }

    function initialize() external initializer {
        __Ownable_init(msg.sender);
    }

    function reportMissingTranscript(
        uint32 ritualId,
        address[] calldata stakingProviders
    ) external {
        // Ritual must have failed
        require(
            coordinator.getRitualState(ritualId) == Coordinator.RitualState.DKG_TIMEOUT,
            "Ritual must have failed"
        );

        for (uint256 i = 0; i < stakingProviders.length; i++) {
            // Check if the infraction has already been reported
            require(
                infractionsForRitual[ritualId][stakingProviders[i]][
                    InfractionType.MISSING_TRANSCRIPT
                ] == 0,
                "Infraction already reported"
            );
            Coordinator.Participant memory participant = coordinator.getParticipantFromProvider(
                ritualId,
                stakingProviders[i]
            );
            require(participant.transcript.length == 0, "Transcript is not missing");
            infractionsForRitual[ritualId][stakingProviders[i]][
                InfractionType.MISSING_TRANSCRIPT
            ] = 1;
            emit InfractionReported(
                ritualId,
                stakingProviders[i],
                InfractionType.MISSING_TRANSCRIPT
            );
        }
    }
}
