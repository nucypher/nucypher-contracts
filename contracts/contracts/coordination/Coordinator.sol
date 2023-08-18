// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControlDefaultAdminRules.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./IFeeModel.sol";
import "./IReimbursementPool.sol";
import "../lib/BLS12381.sol";
import "../../threshold/IAccessControlApplication.sol";
import "./IEncryptionAuthorizer.sol";

/**
* @title Coordinator
* @notice Coordination layer for DKG-TDec
*/
contract Coordinator is AccessControlDefaultAdminRules {

    // Ritual
    event StartRitual(uint32 indexed ritualId, address indexed authority, address[] participants);
    event StartAggregationRound(uint32 indexed ritualId);
    // TODO: Do we want the public key here? If so, we want 2 events or do we reuse this event?
    event EndRitual(uint32 indexed ritualId, bool successful);

    // Node
    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event AggregationPosted(uint32 indexed ritualId, address indexed node, bytes32 aggregatedTranscriptDigest);

    // Admin
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
    event MaxDkgSizeChanged(uint16 oldSize, uint16 newSize);

    event ParticipantPublicKeySet(uint32 indexed ritualId, address indexed participant, BLS12381.G2Point publicKey);

    enum RitualState {
        NON_INITIATED,
        AWAITING_TRANSCRIPTS,
        AWAITING_AGGREGATIONS,
        TIMEOUT,
        INVALID,
        FINALIZED
    }

    struct Participant {
        address provider;
        bool aggregated;
        bytes transcript;  // TODO: Consider event processing complexity vs storage cost
        bytes decryptionRequestStaticKey;
    }

    // TODO: Optimize layout
    struct Ritual {
        address initiator;
        uint32 initTimestamp;
        uint32 endTimestamp;
        uint16 totalTranscripts;
        uint16 totalAggregations;
        address authority;
        uint16 dkgSize;
        bool aggregationMismatch;
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

    mapping(address => ParticipantKey[]) keysHistory;

    IAccessControlApplication public immutable application;

    Ritual[] public rituals;
    uint32 public timeout;
    uint16 public maxDkgSize;
    bool public isInitiationPublic;
    IFeeModel feeModel;  // TODO: Consider making feeModel specific to each ritual
    IReimbursementPool reimbursementPool;
    uint256 public totalPendingFees;
    mapping(uint256 => uint256) public pendingFees;

    constructor(
        IAccessControlApplication _stakes,
        uint32 _timeout,
        uint16 _maxDkgSize,
        address _admin,
        IFeeModel _feeModel
    ) AccessControlDefaultAdminRules(0, _admin)
    {
        require(address(_feeModel.stakes()) == address(_stakes), "Invalid stakes for fee model");
        application = _stakes;
        timeout = _timeout;
        maxDkgSize = _maxDkgSize;
        feeModel = IFeeModel(_feeModel);
    }

    function getRitualState(uint32 ritualId) external view returns (RitualState){
        // TODO: restrict to ritualId < rituals.length?
        return getRitualState(rituals[ritualId]);
    }

    function isRitualFinalized(uint32 ritualId) external view returns (bool){
        return getRitualState(rituals[ritualId]) == RitualState.FINALIZED;
    }

    function getRitualState(Ritual storage ritual) internal view returns (RitualState){
        uint32 t0 = ritual.initTimestamp;
        uint32 deadline = t0 + timeout;
        if (t0 == 0) {
            return RitualState.NON_INITIATED;
        } else if (ritual.totalAggregations == ritual.dkgSize) {
            return RitualState.FINALIZED;
        } else if (ritual.aggregationMismatch) {
            return RitualState.INVALID;
        } else if (block.timestamp > deadline) {
            return RitualState.TIMEOUT;
        } else if (ritual.totalTranscripts < ritual.dkgSize) {
            return RitualState.AWAITING_TRANSCRIPTS;
        } else if (ritual.totalAggregations < ritual.dkgSize) {
            return RitualState.AWAITING_AGGREGATIONS;
        } else {
            // TODO: Is it possible to reach this state?
            //   - No public key
            //   - All transcripts and all aggregations
            //   - Still within the deadline
            revert("Invalid ritual state");
        }
    }

    function makeInitiationPublic() external onlyRole(DEFAULT_ADMIN_ROLE) {
        isInitiationPublic = true;
        _setRoleAdmin(INITIATOR_ROLE, bytes32(0));
    }

    function setProviderPublicKey(BLS12381.G2Point calldata _publicKey) public {
        uint32 lastRitualId = uint32(rituals.length);
        address provider = application.stakingProviderFromOperator(msg.sender);

        ParticipantKey memory newRecord = ParticipantKey(lastRitualId, _publicKey);
        keysHistory[provider].push(newRecord);

        emit ParticipantPublicKeySet(lastRitualId, provider, _publicKey);
    }

    function getProviderPublicKey(address _provider, uint _ritualId) external view returns (BLS12381.G2Point memory) {
        ParticipantKey[] storage participantHistory = keysHistory[_provider];

        for (uint i = participantHistory.length - 1; i >= 0; i--) {
            if (participantHistory[i].lastRitualId <= _ritualId) {
                return participantHistory[i].publicKey;
            }
        }

        revert("No keys found prior to the provided ritual");
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
            address(pool) == address(0) ||
            pool.isAuthorized(address(this)),
            "Invalid ReimbursementPool"
        );
        reimbursementPool = pool;
        // TODO: Events
    }

    function setRitualAuthority(uint32 ritualId, address authority) external {
        Ritual storage ritual = rituals[ritualId];
        require(getRitualState(ritual) == RitualState.FINALIZED, "Ritual not finalized");
        require(msg.sender == ritual.authority, "Sender not ritual authority");
        ritual.authority = authority;
    }

    function numberOfRituals() external view returns (uint256) {
        return rituals.length;
    }

    function getParticipants(uint32 ritualId) external view returns (Participant[] memory) {
        Ritual storage ritual = rituals[ritualId];
        return ritual.participant;
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
        // TODO: Validate service fees, expiration dates, threshold
        uint256 length = providers.length;
        require(2 <= length && length <= maxDkgSize, "Invalid number of nodes");
        require(duration > 0, "Invalid ritual duration");  // TODO: We probably want to restrict it more

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.initiator = msg.sender;
        ritual.authority = authority;
        ritual.dkgSize = uint16(length);
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.endTimestamp = ritual.initTimestamp + duration;
        ritual.accessController = accessController;

        address previous = address(0);
        for (uint256 i = 0; i < length; i++) {
            Participant storage newParticipant = ritual.participant.push();
            address current = providers[i];
            // Make sure that current provider has already set their public key
            ParticipantKey[] storage participantHistory = keysHistory[current];
            require(participantHistory.length > 0, "Provider has not set their public key");

            require(previous < current, "Providers must be sorted");
            // TODO: Improve check for eligible nodes (staking, etc) - nucypher#3109
            // TODO: Change check to isAuthorized(), without amount
            require(
                application.authorizedStake(current) > 0,
                "Not enough authorization"
            );
            newParticipant.provider = current;
            previous = current;
        }

        processRitualPayment(id, providers, duration);

        // TODO: Include cohort fingerprint in StartRitual event?
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
            getRitualState(ritual) == RitualState.AWAITING_TRANSCRIPTS,
            "Not waiting for transcripts"
        );

        address provider = application.stakingProviderFromOperator(msg.sender);
        Participant storage participant = getParticipantFromProvider(ritual, provider);

        require(
            application.authorizedStake(provider) > 0,
            "Not enough authorization"
        );
        require(
            participant.transcript.length == 0,
            "Node already posted transcript"
        );

        // TODO: Validate transcript size based on dkg size

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        participant.transcript = transcript;  // TODO: ???
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
            getRitualState(ritual) == RitualState.AWAITING_AGGREGATIONS,
            "Not waiting for aggregations"
        );

        address provider = application.stakingProviderFromOperator(msg.sender);
        Participant storage participant = getParticipantFromProvider(ritual, provider);
        require(
            application.authorizedStake(provider) > 0,
            "Not enough authorization"
        );

        require(
            !participant.aggregated,
            "Node already posted aggregation"
        );

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
            emit EndRitual({
                ritualId: ritualId,
                successful: false
            });
        }

        if (!ritual.aggregationMismatch) {
            ritual.totalAggregations++;
            if (ritual.totalAggregations == ritual.dkgSize) {
                processPendingFee(ritualId);
                emit EndRitual({
                    ritualId: ritualId,
                    successful: true
                });
                // TODO: Consider including public key in event
            }
        }

        processReimbursement(initialGasLeft);
    }

    function getParticipantFromProvider(
        Ritual storage ritual,
        address provider
    ) internal view returns (Participant storage) {
        uint length = ritual.participant.length;
        // TODO: Improve with binary search
        for (uint i = 0; i < length; i++) {
            Participant storage participant = ritual.participant[i];
            if (participant.provider == provider) {
                return participant;
            }
        }
        revert("Participant not part of ritual");
    }

    function getParticipantFromProvider(
        uint32 ritualId,
        address provider
    ) external view returns (Participant memory) {
        return getParticipantFromProvider(rituals[ritualId], provider);
    }

    function processRitualPayment(uint32 ritualId, address[] calldata providers, uint32 duration) internal {
        uint256 ritualCost = feeModel.getRitualInitiationCost(providers, duration);
        if (ritualCost > 0) {
            totalPendingFees += ritualCost;
            assert(pendingFees[ritualId] == 0);  // TODO: This is an invariant, not sure if actually needed
            pendingFees[ritualId] += ritualCost;
            IERC20 currency = IERC20(feeModel.currency());
            currency.safeTransferFrom(msg.sender, address(this), ritualCost);
            // TODO: Define methods to manage these funds
        }
    }

    function processPendingFee(uint32 ritualId) public {
        Ritual storage ritual = rituals[ritualId];
        RitualState state = getRitualState(ritual);
        require(
            state == RitualState.TIMEOUT ||
            state == RitualState.INVALID ||
            state == RitualState.FINALIZED,
            "Ritual is not ended"
        );
        uint256 pending = pendingFees[ritualId];
        require(pending > 0, "No pending fees for this ritual");

        // Finalize fees for this ritual
        totalPendingFees -= pending;
        delete pendingFees[ritualId];
        // Transfer fees back to initiator if failed
        if (state == RitualState.TIMEOUT || state == RitualState.INVALID) {
            // Amount to refund depends on how much work nodes did for the ritual.
            // TODO: Validate if this is enough to remove griefing attacks
            uint256 executedTransactions = ritual.totalTranscripts + ritual.totalAggregations;
            uint256 expectedTransactions = 2 * ritual.dkgSize;
            uint256 consumedFee = pending * executedTransactions / expectedTransactions;
            uint256 refundableFee = pending - consumedFee;
            IERC20 currency = IERC20(feeModel.currency());
            currency.transferFrom(address(this), ritual.initiator, refundableFee);
        }
    }

    function processReimbursement(uint256 initialGasLeft) internal {
        if (address(reimbursementPool) != address(0)) { // TODO: Consider defining a method
            uint256 gasUsed = initialGasLeft - gasleft();
            try reimbursementPool.refund(gasUsed, msg.sender) {
                return;
            } catch {
                return;
            }
        }
    }
}
