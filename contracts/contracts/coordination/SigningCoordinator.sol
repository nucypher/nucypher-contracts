// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../../threshold/ITACoChildApplication.sol";

contract SigningCoordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable {
    using ECDSA for bytes32;

    struct SigningCohortParticipant {
        address provider;
        bytes signature;
    }

    struct SigningCohort {
        address initiator;
        uint32 initTimestamp;
        uint32 endTimestamp;
        address authority;
        uint16 totalSignatures;
        uint16 numSigners;
        uint16 threshold;
        mapping(address => SigningCohortParticipant) signers;
    }

    mapping(uint256 => SigningCohort) public signingCohorts;
    uint256 public numberOfSigningCohorts;

    event InitiateSigningCohort(
        uint32 indexed cohortId,
        address indexed authority,
        address[] participants
    );
    event SigningCohortSignaturePosted(
        uint32 indexed cohortId,
        address indexed provider,
        bytes signature
    );
    event SigningCohortCompleted(uint32 indexed cohortId);

    enum SigningCohortState {
        NON_INITIATED,
        AWAITING_SIGNATURES,
        TIMEOUT,
        ACTIVE,
        EXPIRED
    }

    ITACoChildApplication public immutable application;
    uint96 private immutable minAuthorization; // TODO use child app for checking eligibility

    uint32 public timeout;
    uint16 public maxCohortSize;

    constructor(ITACoChildApplication _application) {
        application = _application;
        minAuthorization = _application.minimumAuthorization(); // TODO use child app for checking eligibility
        _disableInitializers();
    }

    function initialize(uint32 _timeout, uint16 _maxDkgSize, address _admin) external initializer {
        timeout = _timeout;
        maxCohortSize = _maxDkgSize;
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    function isCohortActive(SigningCohort storage cohort) internal view returns (bool) {
        return getSigningCohortState(cohort) == SigningCohortState.ACTIVE;
    }

    function isCohortActive(uint32 cohortId) external view returns (bool) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return isCohortActive(cohort);
    }

    function setTimeout(uint32 newTimeout) external onlyRole(DEFAULT_ADMIN_ROLE) {
        timeout = newTimeout;
    }

    function isSigner(uint32 cohortId, address provider) external view returns (bool) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        if (cohort.signers[provider].provider != address(0)) {
            return true;
        }
        return false;
    }

    function initiateSigningCohort(
        address authority,
        address[] calldata providers,
        uint16 threshold,
        uint32 duration
    ) external returns (uint32) {
        require(authority != address(0), "Invalid authority");
        uint16 length = uint16(providers.length);
        require(2 <= length && length <= maxCohortSize, "Invalid number of nodes");
        require(threshold > 0 && threshold <= length, "Invalid threshold");
        require(duration >= 24 hours, "Invalid ritual duration");

        uint32 id = uint32(numberOfSigningCohorts);
        SigningCohort storage signingCohort = signingCohorts[id];
        numberOfSigningCohorts += 1;

        signingCohort.initiator = msg.sender;
        signingCohort.authority = authority;
        signingCohort.numSigners = length;
        signingCohort.threshold = threshold;
        signingCohort.initTimestamp = uint32(block.timestamp);
        signingCohort.endTimestamp = signingCohort.initTimestamp + duration;

        for (uint256 i = 0; i < length; i++) {
            address current = providers[i];
            require(
                application.authorizedStake(current) >= minAuthorization,
                "Not enough authorization"
            );
            SigningCohortParticipant storage newParticipant = signingCohort.signers[current];
            newParticipant.provider = current;
        }

        emit InitiateSigningCohort(id, authority, providers);
        return id;
    }

    function postSigningCohortSignature(uint32 cohortId, bytes calldata signature) external {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(
            getSigningCohortState(signingCohort) == SigningCohortState.AWAITING_SIGNATURES,
            "Not waiting for transcripts"
        );
        address provider = application.operatorToStakingProvider(msg.sender);
        require(provider != address(0), "Operator has no bond with staking provider");

        SigningCohortParticipant storage participant = signingCohort.signers[provider];
        require(participant.provider != address(0), "Participant not part of signing ritual");
        require(participant.signature.length == 0, "Node already posted signature");
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        bytes32 dataHash = keccak256(abi.encode(cohortId, signingCohort.authority));
        address recovered = ECDSA.recover(dataHash, signature);
        require(recovered == msg.sender, "Operator signature mismatch");
        require(signingCohort.signers[provider].provider != address(0), "Invalid signer");
        signingCohort.totalSignatures++;

        emit SigningCohortSignaturePosted(cohortId, provider, signature);

        if (signingCohort.totalSignatures == signingCohort.numSigners) {
            emit SigningCohortCompleted(cohortId);
        }
    }

    function getSigningCohortState(
        uint32 signingCohortId
    ) external view returns (SigningCohortState) {
        return getSigningCohortState(signingCohorts[signingCohortId]);
    }

    function getSigningCohortState(
        SigningCohort storage signingCohort
    ) internal view returns (SigningCohortState) {
        uint32 t0 = signingCohort.initTimestamp;
        uint32 deadline = t0 + timeout;
        if (t0 == 0) {
            return SigningCohortState.NON_INITIATED;
        } else if (signingCohort.totalSignatures == signingCohort.numSigners) {
            // DKG was successful
            if (block.timestamp <= signingCohort.endTimestamp) {
                return SigningCohortState.ACTIVE;
            } else {
                return SigningCohortState.EXPIRED;
            }
        } else if (block.timestamp > deadline) {
            // DKG failed due to timeout
            return SigningCohortState.TIMEOUT;
        } else if (signingCohort.totalSignatures < signingCohort.numSigners) {
            return SigningCohortState.AWAITING_SIGNATURES;
        } else {
            /**
             * It shouldn't be possible to reach this state:
             *   - No public key
             *   - All transcripts and all aggregations
             *   - Still within the deadline
             */
            revert("Ambiguous ritual state");
        }
    }
}
