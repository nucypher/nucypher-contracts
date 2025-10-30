// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./IFeeModel.sol";
import "./IReimbursementPool.sol";
import "../lib/BLS12381.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./IEncryptionAuthorizer.sol";

/**
 * @title Coordinator
 * @notice Coordination layer for Threshold Access Control (TACo 🌮)
 */
contract Coordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable {
    using SafeERC20 for IERC20;

    // DKG Protocol
    event StartRitual(uint32 indexed ritualId, address indexed authority, address[] participants);
    event StartAggregationRound(uint32 indexed ritualId);
    event EndRitual(uint32 indexed ritualId, bool successful);
    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event AggregationPosted(
        uint32 indexed ritualId,
        address indexed node,
        bytes32 aggregatedTranscriptDigest
    );

    // Protocol administration
    event MaxDkgSizeChanged(uint16 oldSize, uint16 newSize);
    event ReimbursementPoolSet(address indexed pool);

    // Cohort administration
    event RitualAuthorityTransferred(
        uint32 indexed ritualId,
        address indexed previousAuthority,
        address indexed newAuthority
    );
    event ParticipantPublicKeySet(
        uint32 indexed ritualId,
        address indexed participant,
        BLS12381.G2Point publicKey
    );
    event FeeModelApproved(IFeeModel feeModel);
    event RitualExtended(uint32 indexed ritualId, uint32 endTimestamp);

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

    enum RitualState {
        NON_INITIATED,
        DKG_AWAITING_TRANSCRIPTS,
        DKG_AWAITING_AGGREGATIONS,
        DKG_TIMEOUT,
        DKG_INVALID,
        ACTIVE,
        EXPIRED
    }

    enum HandoverState {
        NON_INITIATED,
        HANDOVER_AWAITING_TRANSCRIPT,
        HANDOVER_AWAITING_BLINDED_SHARE,
        HANDOVER_AWAITING_FINALIZATION,
        HANDOVER_TIMEOUT
    }

    struct Participant {
        address provider;
        bool aggregated;
        bytes transcript;
        bytes decryptionRequestStaticKey;
        // Note: Adjust __postSentinelGap size if this struct's size changes
    }

    struct Handover {
        uint32 requestTimestamp;
        address incomingProvider;
        bytes transcript;
        bytes decryptionRequestStaticKey;
        bytes blindedShare;
    }

    struct Ritual {
        // NOTE: changing the order here affects nucypher/nucypher: CoordinatorAgent
        address initiator;
        uint32 initTimestamp;
        uint32 endTimestamp;
        uint16 totalTranscripts;
        uint16 totalAggregations;
        //
        address authority;
        uint16 dkgSize;
        uint16 threshold;
        bool aggregationMismatch;
        //
        IEncryptionAuthorizer accessController;
        BLS12381.G1Point publicKey;
        bytes aggregatedTranscript;
        Participant[] participant;
        IFeeModel feeModel;
    }

    struct ParticipantKey {
        uint32 lastRitualId;
        BLS12381.G2Point publicKey;
    }

    bytes32 public constant TREASURY_ROLE = keccak256("TREASURY_ROLE");
    bytes32 public constant FEE_MODEL_MANAGER_ROLE = keccak256("FEE_MODEL_MANAGER_ROLE");
    bytes32 public constant HANDOVER_SUPERVISOR_ROLE = keccak256("HANDOVER_SUPERVISOR_ROLE");
    uint256 public constant DECRYPTION_REQUEST_KEY_LENGTH = 42;

    ITACoChildApplication public immutable application;
    uint96 private immutable minAuthorization; // TODO use child app for checking eligibility

    uint32 public immutable dkgTimeout;
    uint32 public immutable handoverTimeout;

    Ritual[] private ritualsStub; // former rituals, "internal" for testing only
    uint32 public dkgTimeoutStub;
    uint16 public maxDkgSize;
    bool private stub1; // former isInitiationPublic

    uint256 private stub2; // former totalPendingFees
    mapping(uint256 => uint256) private stub3; // former pendingFees
    address private stub4; // former feeModel

    IReimbursementPool internal reimbursementPool;
    mapping(address => ParticipantKey[]) internal participantKeysHistory;
    mapping(bytes32 => uint32) internal ritualPublicKeyRegistry;
    mapping(IFeeModel => bool) public feeModelsRegistry;

    mapping(uint256 index => Ritual ritual) public rituals;
    uint256 public numberOfRituals;
    mapping(bytes32 handoverKey => Handover handover) public handovers;
    // Note: Adjust the __preSentinelGap size if more contract variables are added

    // Storage area for sentinel values
    uint256[15] internal __preSentinelGap;
    Participant internal __sentinelParticipant;
    uint256[20] internal __postSentinelGap;

    constructor(ITACoChildApplication _application, uint32 _dkgTimeout, uint32 _handoverTimeout) {
        application = _application;
        dkgTimeout = _dkgTimeout;
        handoverTimeout = _handoverTimeout;
        minAuthorization = _application.minimumAuthorization(); // TODO use child app for checking eligibility
        _disableInitializers();
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(uint16 _maxDkgSize, address _admin) external initializer {
        maxDkgSize = _maxDkgSize;
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    /// @dev for backward compatibility only
    function timeout() external view returns (uint32) {
        return dkgTimeout;
    }

    function getInitiator(uint32 ritualId) external view returns (address) {
        return rituals[ritualId].initiator;
    }

    function getTimestamps(
        uint32 ritualId
    ) external view returns (uint32 initTimestamp, uint32 endTimestamp) {
        Ritual storage ritual = rituals[ritualId];
        initTimestamp = ritual.initTimestamp;
        endTimestamp = ritual.endTimestamp;
    }

    function getAccessController(uint32 ritualId) external view returns (IEncryptionAuthorizer) {
        Ritual storage ritual = rituals[ritualId];
        return ritual.accessController;
    }

    function getFeeModel(uint32 ritualId) external view returns (IFeeModel) {
        Ritual storage ritual = rituals[ritualId];
        return ritual.feeModel;
    }

    function getRitualState(uint32 ritualId) external view returns (RitualState) {
        return getRitualState(rituals[ritualId]);
    }

    function getHandoverState(
        uint32 ritualId,
        address departingParticipant
    ) external view returns (HandoverState) {
        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        return getHandoverState(handover);
    }

    function isRitualActive(Ritual storage ritual) internal view returns (bool) {
        return getRitualState(ritual) == RitualState.ACTIVE;
    }

    function isRitualActive(uint32 ritualId) public view returns (bool) {
        Ritual storage ritual = rituals[ritualId];
        return isRitualActive(ritual);
    }

    function getRitualState(Ritual storage ritual) internal view returns (RitualState) {
        uint32 t0 = ritual.initTimestamp;
        uint32 deadline = t0 + dkgTimeout;
        if (t0 == 0) {
            return RitualState.NON_INITIATED;
        } else if (ritual.totalAggregations == ritual.dkgSize) {
            // DKG was succesful
            if (block.timestamp <= ritual.endTimestamp) {
                return RitualState.ACTIVE;
            } else {
                return RitualState.EXPIRED;
            }
        } else if (ritual.aggregationMismatch) {
            // DKG failed due to invalid transcripts
            return RitualState.DKG_INVALID;
        } else if (block.timestamp > deadline) {
            // DKG failed due to timeout
            return RitualState.DKG_TIMEOUT;
        } else if (ritual.totalTranscripts < ritual.dkgSize) {
            // DKG still waiting for transcripts
            return RitualState.DKG_AWAITING_TRANSCRIPTS;
        } else if (ritual.totalAggregations < ritual.dkgSize) {
            // DKG still waiting for aggregations
            return RitualState.DKG_AWAITING_AGGREGATIONS;
        } else {
            // It shouldn't be possible to reach this state:
            //   - No public key
            //   - All transcripts and all aggregations
            //   - Still within the deadline
            revert("Ambiguous ritual state");
        }
    }

    function getHandoverKey(
        uint32 ritualId,
        address departingProvider
    ) public view returns (bytes32) {
        return keccak256(abi.encode(ritualId, departingProvider));
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

    function setProviderPublicKey(BLS12381.G2Point calldata publicKey) external {
        uint32 lastRitualId = uint32(numberOfRituals);
        address stakingProvider = application.operatorToStakingProvider(msg.sender);
        require(stakingProvider != address(0), "Operator has no bond with staking provider");

        ParticipantKey memory newRecord = ParticipantKey(lastRitualId, publicKey);
        participantKeysHistory[stakingProvider].push(newRecord);

        emit ParticipantPublicKeySet(lastRitualId, stakingProvider, publicKey);
        // solhint-disable-next-line avoid-tx-origin
        require(msg.sender == tx.origin, "Only operator with real address can set public key");
        application.confirmOperatorAddress(msg.sender);
    }

    function getProviderPublicKey(
        address provider,
        uint256 ritualId
    ) external view returns (BLS12381.G2Point memory) {
        ParticipantKey[] storage participantHistory = participantKeysHistory[provider];

        for (uint256 i = participantHistory.length; i > 0; i--) {
            if (participantHistory[i - 1].lastRitualId <= ritualId) {
                return participantHistory[i - 1].publicKey;
            }
        }

        revert("No keys found prior to the provided ritual");
    }

    /**
     * @dev This method is deprecated. Use `isProviderKeySet` instead.
     */
    function isProviderPublicKeySet(address) external view returns (bool) {
        revert("Deprecated method. Upgrade your node to latest version");
    }

    function isProviderKeySet(address provider) public view returns (bool) {
        ParticipantKey[] storage participantHistory = participantKeysHistory[provider];
        return participantHistory.length > 0;
    }

    function setMaxDkgSize(uint16 newSize) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit MaxDkgSizeChanged(maxDkgSize, newSize);
        maxDkgSize = newSize;
    }

    function setReimbursementPool(IReimbursementPool pool) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(
            address(pool) == address(0) || pool.isAuthorized(address(this)),
            "Invalid ReimbursementPool"
        );
        reimbursementPool = pool;
        emit ReimbursementPoolSet(address(pool));
    }

    function transferRitualAuthority(uint32 ritualId, address newAuthority) external {
        Ritual storage ritual = rituals[ritualId];
        require(isRitualActive(ritual), "Ritual is not active");
        address previousAuthority = ritual.authority;
        require(msg.sender == previousAuthority, "Sender not ritual authority");
        ritual.authority = newAuthority;
        emit RitualAuthorityTransferred(ritualId, previousAuthority, newAuthority);
    }

    function getParticipants(uint32 ritualId) external view returns (Participant[] memory) {
        Ritual storage ritual = rituals[ritualId];
        return ritual.participant;
    }

    function getThresholdForRitualSize(uint16 size) public pure returns (uint16) {
        return 1 + size / 2;
        // Alternatively: 1 + 2*size/3 (for >66.6%) or 1 + 3*size/5 (for >60%)
    }

    function initiateRitual(
        IFeeModel feeModel,
        address[] calldata providers,
        address authority,
        uint32 duration,
        IEncryptionAuthorizer accessController
    ) external returns (uint32) {
        require(authority != address(0), "Invalid authority");

        require(feeModelsRegistry[feeModel], "Fee model must be approved");
        uint16 length = uint16(providers.length);
        require(2 <= length && length <= maxDkgSize, "Invalid number of nodes");
        require(duration >= 24 hours, "Invalid ritual duration"); // TODO: Define minimum duration #106

        uint32 id = uint32(numberOfRituals);
        Ritual storage ritual = rituals[id];
        numberOfRituals += 1;
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
            // Make sure that current provider has already set their public key
            ParticipantKey[] storage participantHistory = participantKeysHistory[current];
            require(participantHistory.length > 0, "Provider has not set their public key");

            require(previous < current, "Providers must be sorted");
            // TODO: Improve check for eligible nodes (staking, etc) - nucypher#3109
            // TODO: Change check to isAuthorized(), without amount
            require(
                application.authorizedStake(current) >= minAuthorization,
                "Not enough authorization"
            );
            newParticipant.provider = current;
            previous = current;
        }

        feeModel.processRitualPayment(msg.sender, id, length, duration);

        emit StartRitual(id, ritual.authority, providers);
        return id;
    }

    function cohortFingerprint(address[] calldata nodes) public pure returns (bytes32) {
        return keccak256(abi.encode(nodes));
    }

    function expectedTranscriptSize(
        uint16 dkgSize,
        uint16 threshold
    ) public pure returns (uint256) {
        return 40 + (dkgSize + 1) * BLS12381.G2_POINT_SIZE + threshold * BLS12381.G1_POINT_SIZE;
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

    // /**
    //  * @dev This method is deprecated. Use `publishTranscript` instead.
    //  */
    // function postTranscript(uint32, bytes calldata) external {
    //     revert("Deprecated method. Upgrade your node to latest version");
    // }

    function publishTranscript(uint32 ritualId, bytes calldata transcript) external {
        _postTranscript(ritualId, transcript);
    }

    function _postTranscript(uint32 ritualId, bytes calldata transcript) internal {
        uint256 initialGasLeft = gasleft();

        Ritual storage ritual = rituals[ritualId];
        require(
            getRitualState(ritual) == RitualState.DKG_AWAITING_TRANSCRIPTS,
            "Not waiting for transcripts"
        );

        require(
            transcript.length == expectedTranscriptSize(ritual.dkgSize, ritual.threshold),
            "Invalid transcript size"
        );

        address provider = application.operatorToStakingProvider(msg.sender);
        Participant storage participant = getParticipant(ritual, provider);

        require(application.authorizedStake(provider) > 0, "Not enough authorization");
        require(participant.transcript.length == 0, "Node already posted transcript");

        // TODO: Validate transcript size based on dkg size

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        participant.transcript = transcript;
        emit TranscriptPosted(ritualId, provider, transcriptDigest);
        ritual.totalTranscripts++;

        // end round
        if (ritual.totalTranscripts == ritual.dkgSize) {
            emit StartAggregationRound(ritualId);
        }
        processReimbursement(initialGasLeft);
    }

    function getAuthority(uint32 ritualId) external view returns (address) {
        return rituals[ritualId].authority;
    }

    function postAggregation(
        uint32 ritualId,
        bytes calldata aggregatedTranscript,
        BLS12381.G1Point calldata dkgPublicKey,
        bytes calldata decryptionRequestStaticKey
    ) external {
        uint256 initialGasLeft = gasleft();

        Ritual storage ritual = rituals[ritualId];
        require(
            getRitualState(ritual) == RitualState.DKG_AWAITING_AGGREGATIONS,
            "Not waiting for aggregations"
        );

        address provider = application.operatorToStakingProvider(msg.sender);
        Participant storage participant = getParticipant(ritual, provider);
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        require(!participant.aggregated, "Node already posted aggregation");

        require(
            participant.decryptionRequestStaticKey.length == 0,
            "Node already provided decryption request static key"
        );

        require(
            decryptionRequestStaticKey.length == DECRYPTION_REQUEST_KEY_LENGTH,
            "Invalid length for decryption request static key"
        );

        require(
            aggregatedTranscript.length == expectedTranscriptSize(ritual.dkgSize, ritual.threshold),
            "Invalid transcript size"
        );

        // nodes commit to their aggregation result
        bytes32 aggregatedTranscriptDigest = keccak256(aggregatedTranscript);
        participant.aggregated = true;
        participant.decryptionRequestStaticKey = decryptionRequestStaticKey;
        emit AggregationPosted(ritualId, provider, aggregatedTranscriptDigest);

        if (ritual.aggregatedTranscript.length == 0) {
            ritual.aggregatedTranscript = aggregatedTranscript;
            ritual.publicKey = dkgPublicKey;
        } else if (
            !BLS12381.eqG1Point(ritual.publicKey, dkgPublicKey) ||
            keccak256(ritual.aggregatedTranscript) != aggregatedTranscriptDigest
        ) {
            ritual.aggregationMismatch = true;
            delete ritual.publicKey;
            emit EndRitual({ritualId: ritualId, successful: false});
        }

        if (!ritual.aggregationMismatch) {
            ritual.totalAggregations++;
            if (ritual.totalAggregations == ritual.dkgSize) {
                // processPendingFee(ritualId); TODO consider to notify feeModel
                // Register ritualId + 1 to discern ritualID#0 from unregistered keys.
                // See getRitualIdFromPublicKey() for inverse operation.
                bytes32 registryKey = keccak256(
                    abi.encodePacked(BLS12381.g1PointToBytes(dkgPublicKey))
                );
                ritualPublicKeyRegistry[registryKey] = ritualId + 1;
                emit EndRitual({ritualId: ritualId, successful: true});
            }
        }

        processReimbursement(initialGasLeft);
    }

    function handoverRequest(
        uint32 ritualId,
        address departingParticipant,
        address incomingParticipant
    ) external onlyRole(HANDOVER_SUPERVISOR_ROLE) {
        require(isRitualActive(ritualId), "Ritual is not active");
        require(
            isParticipant(ritualId, departingParticipant),
            "Departing node must be a participant"
        );
        require(
            !isParticipant(ritualId, incomingParticipant),
            "Incoming node cannot be a participant"
        );

        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        HandoverState state = getHandoverState(handover);

        require(
            state == HandoverState.NON_INITIATED || state == HandoverState.HANDOVER_TIMEOUT,
            "Handover already requested"
        );
        require(isProviderKeySet(incomingParticipant), "Incoming provider has not set public key");
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
        require(isRitualActive(ritualId), "Ritual is not active");
        require(transcript.length > 0, "Parameters can't be empty");
        require(
            decryptionRequestStaticKey.length == DECRYPTION_REQUEST_KEY_LENGTH,
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
    }

    function postBlindedShare(uint32 ritualId, bytes calldata blindedShare) external {
        require(isRitualActive(ritualId), "Ritual is not active");

        address provider = application.operatorToStakingProvider(msg.sender);
        Handover storage handover = handovers[getHandoverKey(ritualId, provider)];
        require(
            getHandoverState(handover) == HandoverState.HANDOVER_AWAITING_BLINDED_SHARE,
            "Not waiting for blinded share"
        );
        require(blindedShare.length == BLS12381.G2_POINT_SIZE, "Wrong size of blinded share");

        handover.blindedShare = blindedShare;
        emit BlindedSharePosted(ritualId, provider);
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
        require(isRitualActive(ritualId), "Ritual is not active");

        Handover storage handover = handovers[getHandoverKey(ritualId, departingParticipant)];
        require(
            getHandoverState(handover) == HandoverState.HANDOVER_AWAITING_FINALIZATION,
            "Not waiting for finalization"
        );
        address incomingParticipant = handover.incomingProvider;

        Ritual storage ritual = rituals[ritualId];
        (, Participant storage participant, uint256 participantIndex) = findParticipant(
            ritual,
            departingParticipant
        );
        participant.provider = incomingParticipant;
        participant.decryptionRequestStaticKey = handover.decryptionRequestStaticKey;
        delete participant.transcript;

        uint256 startIndex = blindedSharePosition(participantIndex, ritual.threshold);
        replaceStorageBytes(ritual.aggregatedTranscript, handover.blindedShare, startIndex);
        bytes32 aggregatedTranscriptDigest = keccak256(ritual.aggregatedTranscript);
        emit AggregationPosted(ritualId, incomingParticipant, aggregatedTranscriptDigest);

        handover.requestTimestamp = 0;
        handover.incomingProvider = address(0);
        delete handover.blindedShare;
        delete handover.transcript;
        delete handover.decryptionRequestStaticKey;

        emit HandoverFinalized(ritualId, departingParticipant, incomingParticipant);
        application.release(departingParticipant);
    }

    function replaceStorageBytes(
        bytes storage _preBytes,
        bytes memory _postBytes,
        uint256 startIndex
    ) internal {
        assembly {
            let mlength := mload(_postBytes)

            // get the keccak hash to get the contents of the array
            mstore(0x0, _preBytes.slot)
            // Start copying to the last used word of the stored array.
            let sc := add(keccak256(0x0, 0x20), div(startIndex, 32))

            // Copy over the first `submod` bytes of the new data

            let slengthmod := mod(startIndex, 32)
            let submod := sub(32, slengthmod)
            let mc := add(_postBytes, submod)
            let end := add(_postBytes, mlength)
            let mask := sub(exp(0x100, submod), 1)

            sstore(sc, add(and(sload(sc), not(mask)), and(mload(mc), mask)))

            for {
                sc := add(sc, 1)
                mc := add(mc, 0x20)
            } lt(mc, end) {
                sc := add(sc, 1)
                mc := add(mc, 0x20)
            } {
                sstore(sc, mload(mc))
            }

            mask := sub(exp(0x100, sub(mc, end)), 1)
            sstore(sc, add(and(sload(sc), mask), and(mload(mc), not(mask))))
        }
    }

    function getRitualIdFromPublicKey(
        BLS12381.G1Point memory dkgPublicKey
    ) external view returns (uint32 ritualId) {
        // If public key is not registered, result will produce underflow error
        bytes32 registryKey = keccak256(abi.encodePacked(BLS12381.g1PointToBytes(dkgPublicKey)));
        return ritualPublicKeyRegistry[registryKey] - 1;
    }

    function getPublicKeyFromRitualId(
        uint32 ritualId
    ) external view returns (BLS12381.G1Point memory) {
        Ritual storage ritual = rituals[ritualId];
        RitualState state = getRitualState(ritual);
        require(
            state == RitualState.ACTIVE || state == RitualState.EXPIRED,
            "Ritual not finalized"
        );
        return ritual.publicKey;
    }

    function findParticipant(
        Ritual storage ritual,
        address provider
    ) internal view returns (bool, Participant storage, uint256 index) {
        uint256 length = ritual.participant.length;
        if (length == 0) {
            return (false, __sentinelParticipant, type(uint256).max);
        }
        for (uint256 i = 0; i < length; i++) {
            Participant storage participant = ritual.participant[i];
            if (participant.provider == provider) {
                return (true, participant, i);
            }
        }
        return (false, __sentinelParticipant, type(uint256).max);
    }

    function getParticipant(
        Ritual storage ritual,
        address provider
    ) internal view returns (Participant storage) {
        (bool found, Participant storage participant, ) = findParticipant(ritual, provider);
        require(found, "Participant not part of ritual");
        return participant;
    }

    function getParticipant(
        uint32 ritualId,
        address provider,
        bool transcript
    ) public view returns (Participant memory) {
        Ritual storage ritual = rituals[ritualId];
        Participant memory participant = getParticipant(ritual, provider);
        if (!transcript) {
            participant.transcript = "";
        }
        return participant;
    }

    function getParticipantFromProvider(
        uint32 ritualId,
        address provider
    ) external view returns (Participant memory) {
        return getParticipant(ritualId, provider, true);
    }

    function getParticipants(
        uint32 ritualId,
        uint256 startIndex,
        uint256 maxParticipants,
        bool includeTranscript
    ) external view returns (Participant[] memory) {
        Ritual storage ritual = rituals[ritualId];
        uint256 endIndex = ritual.participant.length;
        require(startIndex >= 0, "Invalid start index");
        require(startIndex < endIndex, "Wrong start index");
        if (maxParticipants != 0 && startIndex + maxParticipants < endIndex) {
            endIndex = startIndex + maxParticipants;
        }
        Participant[] memory ritualParticipants = new Participant[](endIndex - startIndex);

        uint256 resultIndex = 0;
        for (uint256 i = startIndex; i < endIndex; i++) {
            Participant memory ritualParticipant = ritual.participant[i];
            if (!includeTranscript) {
                ritualParticipant.transcript = "";
            }
            ritualParticipants[resultIndex++] = ritualParticipant;
        }

        return ritualParticipants;
    }

    function getProviders(uint32 ritualId) external view returns (address[] memory) {
        Ritual storage ritual = rituals[ritualId];
        address[] memory providers = new address[](ritual.participant.length);
        for (uint256 i = 0; i < ritual.participant.length; i++) {
            providers[i] = ritual.participant[i].provider;
        }
        return providers;
    }

    function isParticipant(uint32 ritualId, address provider) public view returns (bool) {
        Ritual storage ritual = rituals[ritualId];
        (bool found, , ) = findParticipant(ritual, provider);
        return found;
    }

    // /// @dev Deprecated, see issue #195
    // function isEncryptionAuthorized(
    //     uint32,
    //     bytes memory,
    //     bytes memory
    // ) external view returns (bool) {
    //     revert("Deprecated method. Upgrade your node to latest version");
    // }

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

    function approveFeeModel(IFeeModel feeModel) external onlyRole(FEE_MODEL_MANAGER_ROLE) {
        require(!feeModelsRegistry[feeModel], "Fee model already approved");
        feeModelsRegistry[feeModel] = true;
        emit FeeModelApproved(feeModel);
    }

    function extendRitual(uint32 ritualId, uint32 duration) external onlyRole(DEFAULT_ADMIN_ROLE) {
        Ritual storage ritual = rituals[ritualId];
        // require(msg.sender == ritual.initiator, "Only initiator can extend ritual"); // TODO temp only, uncomment when ready
        require(getRitualState(ritual) == RitualState.ACTIVE, "Only active ritual can be extended");
        ritual.endTimestamp += duration;
        ritual.feeModel.processRitualExtending(
            ritual.initiator,
            ritualId,
            ritual.participant.length,
            duration
        );
        emit RitualExtended(ritualId, ritual.endTimestamp);
    }

    // function withdrawAllTokens(IERC20 token) external onlyRole(TREASURY_ROLE) {
    //     uint256 tokenBalance = token.balanceOf(address(this));
    //     require(tokenBalance > 0, "Insufficient balance");
    //     token.safeTransfer(msg.sender, tokenBalance);
    // }
}
