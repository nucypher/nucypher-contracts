// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./FlatRateFeeModel.sol";
import "./IReimbursementPool.sol";
import "../lib/BLS12381.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./IEncryptionAuthorizer.sol";

/**
 * @title Coordinator
 * @notice Coordination layer for Threshold Access Control (TACo 🌮)
 */
contract Coordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable, FlatRateFeeModel {
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
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
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

    enum RitualState {
        NON_INITIATED,
        DKG_AWAITING_TRANSCRIPTS,
        DKG_AWAITING_AGGREGATIONS,
        DKG_TIMEOUT,
        DKG_INVALID,
        ACTIVE,
        EXPIRED
    }

    struct Participant {
        address provider;
        bool aggregated;
        bytes transcript;
        bytes decryptionRequestStaticKey;
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
    }

    struct ParticipantKey {
        uint32 lastRitualId;
        BLS12381.G2Point publicKey;
    }

    using SafeERC20 for IERC20;

    bytes32 public constant INITIATOR_ROLE = keccak256("INITIATOR_ROLE");
    bytes32 public constant TREASURY_ROLE = keccak256("TREASURY_ROLE");

    ITACoChildApplication public immutable application;
    uint96 private immutable minAuthorization;

    Ritual[] public rituals;
    uint32 public timeout;
    uint16 public maxDkgSize;
    bool public isInitiationPublic;
    uint256 public totalPendingFees;
    mapping(uint256 => uint256) public pendingFees;
    IFeeModel internal feeModel; // TODO: Consider making feeModel specific to each ritual
    IReimbursementPool internal reimbursementPool;
    mapping(address => ParticipantKey[]) internal participantKeysHistory;
    mapping(bytes32 => uint32) internal ritualPublicKeyRegistry;
    Participant internal SENTINEL_PARTICIPANT;

    constructor(
        ITACoChildApplication _application,
        IERC20 _currency,
        uint256 _feeRatePerSecond
    ) FlatRateFeeModel(_currency, _feeRatePerSecond) {
        application = _application;
        minAuthorization = _application.minimumAuthorization();
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(uint32 _timeout, uint16 _maxDkgSize, address _admin) external initializer {
        timeout = _timeout;
        maxDkgSize = _maxDkgSize;
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    function getRitualState(uint32 ritualId) external view returns (RitualState) {
        return getRitualState(rituals[ritualId]);
    }

    function isRitualActive(Ritual storage ritual) internal view returns (bool) {
        return getRitualState(ritual) == RitualState.ACTIVE;
    }

    function isRitualActive(uint32 ritualId) external view returns (bool) {
        Ritual storage ritual = rituals[ritualId];
        return isRitualActive(ritual);
    }

    function getRitualState(Ritual storage ritual) internal view returns (RitualState) {
        uint32 t0 = ritual.initTimestamp;
        uint32 deadline = t0 + timeout;
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
            assert(false);
        }
    }

    function makeInitiationPublic() external onlyRole(DEFAULT_ADMIN_ROLE) {
        isInitiationPublic = true;
        _setRoleAdmin(INITIATOR_ROLE, bytes32(0));
    }

    function setProviderPublicKey(BLS12381.G2Point calldata _publicKey) external {
        uint32 lastRitualId = uint32(rituals.length);
        address stakingProvider = application.operatorToStakingProvider(msg.sender);
        require(stakingProvider != address(0), "Operator has no bond with staking provider");

        ParticipantKey memory newRecord = ParticipantKey(lastRitualId, _publicKey);
        participantKeysHistory[stakingProvider].push(newRecord);

        emit ParticipantPublicKeySet(lastRitualId, stakingProvider, _publicKey);
        // solhint-disable-next-line avoid-tx-origin
        require(msg.sender == tx.origin, "Only operator with real address can set public key");
        application.confirmOperatorAddress(msg.sender);
    }

    function getProviderPublicKey(
        address _provider,
        uint256 _ritualId
    ) external view returns (BLS12381.G2Point memory) {
        ParticipantKey[] storage participantHistory = participantKeysHistory[_provider];

        for (uint256 i = participantHistory.length; i > 0; i--) {
            if (participantHistory[i - 1].lastRitualId <= _ritualId) {
                return participantHistory[i - 1].publicKey;
            }
        }

        revert("No keys found prior to the provided ritual");
    }

    function isProviderPublicKeySet(address _provider) external view returns (bool) {
        ParticipantKey[] storage participantHistory = participantKeysHistory[_provider];
        return participantHistory.length > 0;
    }

    function setTimeout(uint32 newTimeout) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit TimeoutChanged(timeout, newTimeout);
        timeout = newTimeout;
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

    function numberOfRituals() external view returns (uint256) {
        return rituals.length;
    }

    function getThresholdForRitualSize(uint16 size) public pure returns (uint16) {
        return 1 + size / 2;
        // Alternatively: 1 + 2*size/3 (for >66.6%) or 1 + 3*size/5 (for >60%)
    }

    function initiateRitual(
        address[] calldata providers,
        address authority,
        uint32 duration,
        IEncryptionAuthorizer accessController
    ) external returns (uint32) {
        require(authority != address(0), "Invalid authority");

        require(
            isInitiationPublic || hasRole(INITIATOR_ROLE, msg.sender),
            "Sender can't initiate ritual"
        );
        uint16 length = uint16(providers.length);
        require(2 <= length && length <= maxDkgSize, "Invalid number of nodes");
        require(duration >= 24 hours, "Invalid ritual duration"); // TODO: Define minimum duration #106

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.initiator = msg.sender;
        ritual.authority = authority;
        ritual.dkgSize = length;
        ritual.threshold = getThresholdForRitualSize(length);
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.endTimestamp = ritual.initTimestamp + duration;
        ritual.accessController = accessController;

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

        processRitualPayment(id, providers, duration);

        emit StartRitual(id, ritual.authority, providers);
        return id;
    }

    function cohortFingerprint(address[] calldata nodes) public pure returns (bytes32) {
        return keccak256(abi.encode(nodes));
    }

    function postTranscript(uint32 ritualId, bytes calldata transcript) external {
        uint256 initialGasLeft = gasleft();

        Ritual storage ritual = rituals[ritualId];
        require(
            getRitualState(ritual) == RitualState.DKG_AWAITING_TRANSCRIPTS,
            "Not waiting for transcripts"
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
            decryptionRequestStaticKey.length == 42,
            "Invalid length for decryption request static key"
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
                processPendingFee(ritualId);
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

    function getRitualIdFromPublicKey(
        BLS12381.G1Point memory dkgPublicKey
    ) external view returns (uint32 ritualId) {
        // If public key is not registered, result will produce underflow error
        bytes32 registryKey = keccak256(abi.encodePacked(BLS12381.g1PointToBytes(dkgPublicKey)));
        return ritualPublicKeyRegistry[registryKey] - 1;
    }

    function getPublicKeyFromRitualId(
        uint32 ritualId
    ) external view returns (BLS12381.G1Point memory dkgPublicKey) {
        Ritual storage ritual = rituals[ritualId];
        RitualState state = getRitualState(ritual);
        require(
            state == RitualState.ACTIVE || state == RitualState.EXPIRED,
            "Ritual not finalized"
        );
        return ritual.publicKey;
    }

    function _getParticipant(
        Ritual storage ritual,
        address provider
    ) internal view returns (bool, uint256, Participant storage participant) {
        uint256 low = 0;
        uint256 high = ritual.participant.length - 1;
        while (low <= high) {
            uint256 mid = low + (high - low) / 2;
            Participant storage participant = ritual.participant[mid];
            if (participant.provider < provider) {
                low = mid + 1;
            } else if (participant.provider > provider) {
                high = mid - 1;
            } else {
                return (true, mid, participant);
            }
        }
        return (false, 0, SENTINEL_PARTICIPANT);
    }

    function getParticipant(
        Ritual storage ritual,
        address provider
    ) internal view returns (Participant storage) {
        (bool found,, Participant storage participant) = _getParticipant(ritual, provider);
        require(found, "Participant not found");
        return participant;
    }

    function getParticipant(
        uint32 ritualId,
        address provider,
        bool transcripts
    ) external view returns (Participant memory, uint256) {
        Ritual storage ritual = rituals[ritualId];
        (bool found, uint256 index, Participant memory participant) = _getParticipant(ritual, provider);
        require(found, "Participant not found");
        if (!transcripts) {
            participant.transcript = '';
        }
        return (participant, index);
    }

    function isParticipant(uint32 ritualId, address provider) external view returns (bool, uint256) {
        Ritual storage ritual = rituals[ritualId];
        (bool found, uint256 index,) = _getParticipant(ritual, provider);
        return (found, index);
    }

    function isEncryptionAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) external view returns (bool) {
        Ritual storage ritual = rituals[ritualId];
        require(getRitualState(ritual) == RitualState.ACTIVE, "Ritual not active");
        return ritual.accessController.isAuthorized(ritualId, evidence, ciphertextHeader);
    }

    function processRitualPayment(
        uint32 ritualId,
        address[] calldata providers,
        uint32 duration
    ) internal {
        uint256 ritualCost = getRitualInitiationCost(providers, duration);
        require(ritualCost > 0, "Invalid ritual cost");
        totalPendingFees += ritualCost;
        pendingFees[ritualId] = ritualCost;
        currency.safeTransferFrom(msg.sender, address(this), ritualCost);
    }

    function processPendingFee(uint32 ritualId) public returns (uint256 refundableFee) {
        Ritual storage ritual = rituals[ritualId];
        RitualState state = getRitualState(ritual);
        require(
            state == RitualState.DKG_TIMEOUT ||
                state == RitualState.DKG_INVALID ||
                state == RitualState.ACTIVE ||
                state == RitualState.EXPIRED,
            "Ritual is not ended"
        );
        uint256 pending = pendingFees[ritualId];
        require(pending > 0, "No pending fees for this ritual");

        // Finalize fees for this ritual
        totalPendingFees -= pending;
        delete pendingFees[ritualId];
        // Transfer fees back to initiator if failed
        if (state == RitualState.DKG_TIMEOUT || state == RitualState.DKG_INVALID) {
            // Refund everything minus cost of renting cohort for a day
            uint256 duration = ritual.endTimestamp - ritual.initTimestamp;
            refundableFee = pending - feeDeduction(pending, duration);
            currency.safeTransfer(ritual.initiator, refundableFee);
        }
        return refundableFee;
    }

    function processReimbursement(uint256 initialGasLeft) internal {
        if (address(reimbursementPool) != address(0)) {
            uint256 gasUsed = initialGasLeft - gasleft();
            try reimbursementPool.refund(gasUsed, msg.sender) {
                return;
            } catch {
                return;
            }
        }
    }

    function withdrawTokens(IERC20 token, uint256 amount) external onlyRole(TREASURY_ROLE) {
        if (address(token) == address(currency)) {
            require(
                amount <= token.balanceOf(address(this)) - totalPendingFees,
                "Can't withdraw pending fees"
            );
        }
        token.safeTransfer(msg.sender, amount);
    }
}
