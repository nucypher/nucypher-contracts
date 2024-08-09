// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./Coordinator.sol";
import "../../threshold/ITACoChildApplication.sol";

contract InfractionCollector is OwnableUpgradeable {
    Coordinator public immutable coordinator;

    // Reference to the TACoChildApplication contract
    ITACoChildApplication public immutable tacoChildApplication;

    // infraction types
    enum InfractionType {
        MISSING_TRANSCRIPT
    }

    // Mapping to keep track of reported infractions
    mapping(uint32 => mapping(address => mapping(InfractionType => bool))) public infractions;

    constructor(Coordinator _coordinator, ITACoChildApplication _tacoChildApplication) {
        coordinator = _coordinator;
        tacoChildApplication = _tacoChildApplication;
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
                !infractions[ritualId][stakingProviders[i]][InfractionType.MISSING_TRANSCRIPT],
                "Infraction already reported"
            );
            Coordinator.Participant memory participant = coordinator.getParticipantFromProvider(
                ritualId,
                stakingProviders[i]
            );
            if (participant.transcript.length == 0) {
                // Transcript TX wasn't posted
                // Penalize the staking provider
                // tacoChildApplication.penalize(stakingProviders[i]);
                infractions[ritualId][stakingProviders[i]][
                    InfractionType.MISSING_TRANSCRIPT
                ] = true;
            }
        }
    }
}
