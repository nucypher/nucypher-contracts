// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./Coordinator.sol";

/**
 * @title HandoverCoordinator
 * @notice Coordination layer for Handover protocol
 */
contract HandoverCoordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable {
    event ReimbursementPoolSet(address indexed pool);
    event HandoverRequest(
        uint32 indexed ritualId,
        address indexed departingParticipant,
        address indexed incomingParticipant
    );
    event HandoverTranscriptPosted(
        uint32 indexed ritualId,
        address indexed departingParticipant,
        address indexed incomingParticipant
    );
    event BlindedSharePosted(uint32 indexed ritualId, address indexed departingParticipant);
    event HandoverCanceled(
        uint32 indexed ritualId,
        address indexed departingParticipant,
        address indexed incomingParticipant
    );
    event HandoverFinalized(
        uint32 indexed ritualId,
        address indexed departingParticipant,
        address indexed incomingParticipant
    );

    enum HandoverState {
        NON_INITIATED,
        HANDOVER_AWAITING_TRANSCRIPT,
        HANDOVER_AWAITING_BLINDED_SHARE,
        HANDOVER_AWAITING_FINALIZATION,
        HANDOVER_TIMEOUT
    }

    struct Handover {
        uint32 requestTimestamp;
        address incomingProvider;
        bytes transcript;
        bytes decryptionRequestStaticKey;
        bytes blindedShare;
    }

    bytes32 public constant HANDOVER_SUPERVISOR_ROLE = keccak256("HANDOVER_SUPERVISOR_ROLE");

    ITACoChildApplication public immutable application;
    Coordinator public immutable coordinator;
    uint32 public immutable handoverTimeout;
    uint96 private immutable minAuthorization; // TODO use child app for checking eligibility

    IReimbursementPool internal reimbursementPool;
    mapping(bytes32 handoverKey => Handover handover) public handovers;
    // Note: Adjust the __preSentinelGap size if more contract variables are added

    uint256[20] internal __gap;

    constructor(
        ITACoChildApplication _application,
        Coordinator _coordinator,
        uint32 _handoverTimeout
    ) {
        application = _application;
        coordinator = _coordinator;
        handoverTimeout = _handoverTimeout;
        minAuthorization = _application.minimumAuthorization(); // TODO use child app for checking eligibility
        _disableInitializers();
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(address _admin) external initializer {
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    function setReimbursementPool(IReimbursementPool pool) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(
            address(pool) == address(0) || pool.isAuthorized(address(this)),
            "Invalid ReimbursementPool"
        );
        reimbursementPool = pool;
        emit ReimbursementPoolSet(address(pool));
    }

    function processReimbursement(uint256 initialGasLeft) internal {
        if (address(reimbursementPool) != address(0)) {
            // For calldataGasCost calculation, see https://github.com/nucypher/nucypher-contracts/issues/328
            uint256 calldataGasCost = (msg.data.length - 128) * 16 + 128 * 4;
            uint256 gasUsed = initialGasLeft - gasleft() + calldataGasCost;
            try reimbursementPool.refund(gasUsed, msg.sender) {
                return;
            } catch {
                return;
            }
        }
    }

    function getHandoverKey(
        uint32 ritualId,
        address departingProvider
    ) public view returns (bytes32) {
        return keccak256(abi.encode(ritualId, departingProvider));
    }

    function getHandoverState(
        uint32 ritualId,
        address departingParticipant
    ) external view returns (HandoverState) {
        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        return getHandoverState(handover);
    }

    function getHandoverState(Handover storage handover) internal view returns (HandoverState) {
        uint32 t0 = handover.requestTimestamp;
        uint32 deadline = t0 + handoverTimeout;
        if (t0 == 0) {
            return HandoverState.NON_INITIATED;
        } else if (block.timestamp > deadline) {
            // Handover failed due to timeout
            return HandoverState.HANDOVER_TIMEOUT;
        } else if (handover.transcript.length == 0) {
            return HandoverState.HANDOVER_AWAITING_TRANSCRIPT;
        } else if (handover.blindedShare.length == 0) {
            return HandoverState.HANDOVER_AWAITING_BLINDED_SHARE;
        } else {
            return HandoverState.HANDOVER_AWAITING_FINALIZATION;
        }
    }

    /**
     * Calculates position of blinded share for particular participant
     * @param index Participant index
     * @param threshold Threshold
     * @dev See https://github.com/nucypher/nucypher-contracts/issues/400
     */
    function blindedSharePosition(uint256 index, uint16 threshold) public pure returns (uint256) {
        return 32 + index * BLS12381.G2_POINT_SIZE + threshold * BLS12381.G1_POINT_SIZE;
    }

    function handoverRequest(
        uint32 ritualId,
        address departingParticipant,
        address incomingParticipant
    ) external onlyRole(HANDOVER_SUPERVISOR_ROLE) {
        require(coordinator.isRitualActive(ritualId), "Ritual is not active");
        require(
            coordinator.isParticipant(ritualId, departingParticipant),
            "Departing node must be a participant"
        );
        require(
            !coordinator.isParticipant(ritualId, incomingParticipant),
            "Incoming node cannot be a participant"
        );

        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        HandoverState state = getHandoverState(handover);

        require(
            state == HandoverState.NON_INITIATED || state == HandoverState.HANDOVER_TIMEOUT,
            "Handover already requested"
        );
        require(
            coordinator.isProviderKeySet(incomingParticipant),
            "Incoming provider has not set public key"
        );
        require(
            application.authorizedStake(incomingParticipant) >= minAuthorization,
            "Not enough authorization"
        );
        handover.requestTimestamp = uint32(block.timestamp);
        handover.incomingProvider = incomingParticipant;
        delete handover.blindedShare;
        delete handover.transcript;
        delete handover.decryptionRequestStaticKey;
        emit HandoverRequest(ritualId, departingParticipant, incomingParticipant);
    }

    function postHandoverTranscript(
        uint32 ritualId,
        address departingParticipant,
        bytes calldata transcript,
        bytes calldata decryptionRequestStaticKey
    ) external {
        uint256 initialGasLeft = gasleft();
        require(coordinator.isRitualActive(ritualId), "Ritual is not active");
        require(transcript.length > 0, "Parameters can't be empty");
        require(
            decryptionRequestStaticKey.length == 42,
            "Invalid length for decryption request static key"
        );

        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        require(
            getHandoverState(handover) == HandoverState.HANDOVER_AWAITING_TRANSCRIPT,
            "Not waiting for transcript"
        );
        address provider = application.operatorToStakingProvider(msg.sender);
        require(handover.incomingProvider == provider, "Wrong incoming provider");

        handover.transcript = transcript;
        handover.decryptionRequestStaticKey = decryptionRequestStaticKey;
        emit HandoverTranscriptPosted(ritualId, departingParticipant, provider);
        processReimbursement(initialGasLeft);
    }

    function postBlindedShare(uint32 ritualId, bytes calldata blindedShare) external {
        uint256 initialGasLeft = gasleft();
        require(coordinator.isRitualActive(ritualId), "Ritual is not active");

        address provider = application.operatorToStakingProvider(msg.sender);
        Handover storage handover = handovers[getHandoverKey(ritualId, provider)];
        require(
            getHandoverState(handover) == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE,
            "Not waiting for blinded share"
        );
        require(blindedShare.length == BLS12381.G2_POINT_SIZE, "Wrong size of blinded share");

        handover.blindedShare = blindedShare;
        emit BlindedSharePosted(ritualId, provider);
        processReimbursement(initialGasLeft);
    }

    function cancelHandover(
        uint32 ritualId,
        address departingParticipant
    ) external onlyRole(HANDOVER_SUPERVISOR_ROLE) {
        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        address incomingParticipant = handover.incomingProvider;

        require(
            getHandoverState(handover) != HandoverState.NON_INITIATED,
            "Handover not requested"
        );
        handover.requestTimestamp = 0;
        handover.incomingProvider = address(0);
        delete handover.blindedShare;
        delete handover.transcript;
        delete handover.decryptionRequestStaticKey;

        emit HandoverCanceled(ritualId, departingParticipant, incomingParticipant);
    }

    function finalizeHandover(
        uint32 ritualId,
        address departingParticipant
    ) external onlyRole(HANDOVER_SUPERVISOR_ROLE) {
        require(coordinator.isRitualActive(ritualId), "Ritual is not active");

        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        require(
            getHandoverState(handover) == HandoverState.HANDOVER_AWAITING_FINALIZATION,
            "Not waiting for finalization"
        );
        address incomingParticipant = handover.incomingProvider;

        Coordinator.Participant[] memory participants = coordinator.getParticipants(ritualId);
        uint256 participantIndex = findParticipant(participants, departingParticipant);
        coordinator.updateParticipant(
            ritualId,
            departingParticipant,
            incomingParticipant,
            true,
            new bytes(0),
            handover.decryptionRequestStaticKey
        );

        uint16 threshold = coordinator.getThreshold(ritualId);
        uint256 startIndex = blindedSharePosition(participantIndex, threshold);
        coordinator.replaceAggregatedTranscriptBytes(
            ritualId,
            incomingParticipant,
            handover.blindedShare,
            startIndex
        );

        handover.requestTimestamp = 0;
        handover.incomingProvider = address(0);
        delete handover.blindedShare;
        delete handover.transcript;
        delete handover.decryptionRequestStaticKey;

        emit HandoverFinalized(ritualId, departingParticipant, incomingParticipant);
        application.release(departingParticipant);
    }

    function findParticipant(
        Coordinator.Participant[] memory participants,
        address provider
    ) internal view returns (uint256 index) {
        for (uint256 i = 0; i < participants.length; i++) {
            Coordinator.Participant memory participant = participants[i];
            if (participant.provider == provider) {
                return i;
            }
        }
    }
}
