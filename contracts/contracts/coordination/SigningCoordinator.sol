// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./ThresholdSigningMultisigCloneFactory.sol";

contract SigningCoordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable {
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    struct SigningCohortParticipant {
        address provider;
        address operator;
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
        address multisig;
        SigningCohortParticipant[] signers;
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
    event SigningCohortCompleted(uint32 indexed cohortId, address multisig);

    enum SigningCohortState {
        NON_INITIATED,
        AWAITING_SIGNATURES,
        TIMEOUT,
        ACTIVE,
        EXPIRED
    }

    ITACoChildApplication public immutable application;
    ThresholdSigningMultisigCloneFactory public immutable signingMultisigFactory;
    uint96 private immutable minAuthorization; // TODO use child app for checking eligibility

    uint32 public timeout;
    uint16 public maxCohortSize;

    SigningCohortParticipant internal __sentinelSigner;

    constructor(
        ITACoChildApplication _application,
        ThresholdSigningMultisigCloneFactory _signingMultisigFactory
    ) {
        application = _application;
        signingMultisigFactory = _signingMultisigFactory;
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

    function findSigner(
        SigningCohort storage cohort,
        address provider
    ) internal view returns (bool, SigningCohortParticipant storage) {
        uint256 length = cohort.signers.length;
        if (length == 0) {
            return (false, __sentinelSigner);
        }
        uint256 low = 0;
        uint256 high = length - 1;
        while (low <= high) {
            uint256 mid = (low + high) / 2;
            SigningCohortParticipant storage middleParticipant = cohort.signers[mid];
            if (middleParticipant.provider == provider) {
                return (true, middleParticipant);
            } else if (middleParticipant.provider < provider) {
                low = mid + 1;
            } else {
                if (mid == 0) {
                    // prevent underflow of unsigned int
                    break;
                }
                high = mid - 1;
            }
        }
        return (false, __sentinelSigner);
    }

    function isSigner(uint32 cohortId, address provider) external view returns (bool) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        (bool found, ) = findSigner(cohort, provider);
        return found;
    }

    function getSigner(
        SigningCohort storage cohort,
        address provider
    ) internal view returns (SigningCohortParticipant storage) {
        (bool found, SigningCohortParticipant storage participant) = findSigner(cohort, provider);
        require(found, "Participant not part of ritual");
        return participant;
    }

    function getSigner(
        uint32 cohortId,
        address provider
    ) external view returns (SigningCohortParticipant memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        SigningCohortParticipant memory participant = getSigner(cohort, provider);
        return participant;
    }

    function getSigners(uint32 cohortId) external view returns (SigningCohortParticipant[] memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.signers;
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

        address previous = address(0);
        for (uint256 i = 0; i < length; i++) {
            address current = providers[i];
            require(
                application.authorizedStake(current) >= minAuthorization,
                "Not enough authorization"
            );
            require(previous < current, "Providers must be sorted");
            SigningCohortParticipant storage newParticipant = signingCohort.signers.push();
            newParticipant.provider = current;
            previous = current;
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

        SigningCohortParticipant storage participant = getSigner(signingCohort, provider);
        require(participant.provider != address(0), "Participant not part of signing ritual");
        require(participant.signature.length == 0, "Node already posted signature");
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        bytes32 dataHash = keccak256(abi.encode(cohortId, signingCohort.authority));
        address recovered = dataHash.toEthSignedMessageHash().recover(signature);
        require(recovered == msg.sender, "Operator signature mismatch");

        participant.operator = msg.sender;
        participant.signature = signature;
        signingCohort.totalSignatures++;

        emit SigningCohortSignaturePosted(cohortId, provider, signature);

        if (signingCohort.totalSignatures == signingCohort.numSigners) {
            address[] memory signers = new address[](signingCohort.numSigners);
            for (uint256 i = 0; i < signingCohort.signers.length; i++) {
                // ursula operator address does signing; not staking provider
                signers[i] = signingCohort.signers[i].operator;
            }
            address signingMultisig = deploySigningMultisig(
                cohortId,
                signers,
                signingCohort.threshold
            );
            signingCohort.multisig = signingMultisig;

            emit SigningCohortCompleted(cohortId, signingMultisig);
        }
    }

    function deploySigningMultisig(
        uint32 cohortId,
        address[] memory signers,
        uint16 threshold
    ) internal returns (address) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(signingCohort.totalSignatures == signingCohort.numSigners, "Not enough signatures");
        require(signingCohort.multisig == address(0), "Already deployed");
        return
            signingMultisigFactory.deploySigningMultisig(
                signers,
                threshold,
                signingCohort.authority,
                cohortId
            );
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
        } else if (signingCohort.multisig != address(0)) {
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
