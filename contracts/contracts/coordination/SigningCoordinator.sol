// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./ISigningCoordinatorChild.sol";
import "./ThresholdSigningMultisigCloneFactory.sol";
import "./SigningCoordinatorDispatcher.sol";

// SigningCoordinator ----> Dispatcher ----> (Relevant) L1Sender ---------[BRIDGE]---------- L2Receiver ----> SigningCoordinatorChild (1. deploys multisig OR 2. updates multisig)

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
        // TODO: what's the point of authority if we have a single global cohort?
        address authority;
        uint16 totalSignatures;
        uint16 numSigners;
        uint16 threshold;
        SigningCohortParticipant[] signers;
        uint256[] chains;
        mapping(uint256 => bytes) conditions; // TODO: chainId -> condition itself or hash(condition)
    }

    bytes32 public constant INITIATOR_ROLE = keccak256("INITIATOR_ROLE");

    mapping(uint32 => SigningCohort) public signingCohorts;
    uint256 public numberOfSigningCohorts;

    event InitiateSigningCohort(
        uint32 indexed cohortId,
        uint256 chainId,
        address indexed authority,
        address[] participants
    );
    event SigningCohortSignaturePosted(
        uint32 indexed cohortId,
        address indexed provider,
        bytes signature
    );
    event SigningCohortDeployed(uint32 indexed cohortId, uint256 chainId);
    event SigningCohortConditionsSet(uint32 indexed cohortId, uint256 chainId, bytes conditions);

    enum SigningCohortState {
        NON_INITIATED,
        AWAITING_SIGNATURES,
        TIMEOUT,
        ACTIVE,
        EXPIRED
    }

    ITACoChildApplication public immutable application;
    SigningCoordinatorDispatcher public immutable signingCoordinatorDispatcher;

    uint96 private immutable minAuthorization; // TODO use child app for checking eligibility

    uint32 public timeout;
    uint16 public maxCohortSize;

    SigningCohortParticipant internal __sentinelSigner;

    constructor(
        ITACoChildApplication _application,
        SigningCoordinatorDispatcher _signingCoordinatorDispatcher
    ) {
        application = _application;
        signingCoordinatorDispatcher = _signingCoordinatorDispatcher;
        minAuthorization = _application.minimumAuthorization(); // TODO use child app for checking eligibility
        _disableInitializers();
    }

    function initialize(uint32 _timeout, uint16 _maxDkgSize, address _admin) external initializer {
        timeout = _timeout;
        maxCohortSize = _maxDkgSize;
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    function _isCohortActive(SigningCohort storage _cohort) internal view returns (bool) {
        return _getSigningCohortState(_cohort) == SigningCohortState.ACTIVE;
    }

    function isCohortActive(uint32 cohortId) external view returns (bool) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return _isCohortActive(cohort);
    }

    function setTimeout(uint32 newTimeout) external onlyRole(DEFAULT_ADMIN_ROLE) {
        timeout = newTimeout;
    }

    function _findSigner(
        SigningCohort storage _cohort,
        address _provider
    ) internal view returns (bool, SigningCohortParticipant storage) {
        uint256 length = _cohort.signers.length;
        if (length == 0) {
            return (false, __sentinelSigner);
        }
        uint256 low = 0;
        uint256 high = length - 1;
        while (low <= high) {
            uint256 mid = (low + high) / 2;
            SigningCohortParticipant storage middleParticipant = _cohort.signers[mid];
            if (middleParticipant.provider == _provider) {
                return (true, middleParticipant);
            } else if (middleParticipant.provider < _provider) {
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
        (bool found, ) = _findSigner(cohort, provider);
        return found;
    }

    function _getSigner(
        SigningCohort storage _cohort,
        address _provider
    ) internal view returns (SigningCohortParticipant storage) {
        (bool found, SigningCohortParticipant storage participant) = _findSigner(
            _cohort,
            _provider
        );
        require(found, "Participant not part of ritual");
        return participant;
    }

    function getSigner(
        uint32 cohortId,
        address provider
    ) external view returns (SigningCohortParticipant memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        SigningCohortParticipant memory participant = _getSigner(cohort, provider);
        return participant;
    }

    function getSigners(uint32 cohortId) external view returns (SigningCohortParticipant[] memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.signers;
    }

    function getChains(uint32 cohortId) external view returns (uint256[] memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.chains;
    }

    function getCondition(uint32 cohortId, uint256 chainId) external view returns (bytes memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.conditions[chainId];
    }

    function initiateSigningCohort(
        uint256 chainId,
        address authority,
        address[] calldata providers,
        uint16 threshold,
        uint32 duration
    )
        external
        // TODO initiator role needed for now
        onlyRole(INITIATOR_ROLE)
        returns (uint32)
    {
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
        signingCohort.chains.push(chainId);

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
        emit InitiateSigningCohort(id, chainId, authority, providers);
        return id;
    }

    function setSigningCohortConditions(
        uint32 cohortId,
        uint256 chainId,
        bytes calldata conditions
    ) external {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(_isCohortActive(signingCohort), "Cohort not active");
        require(
            signingCohort.authority == msg.sender,
            "Only the cohort authority can set conditions"
        );
        signingCohort.conditions[chainId] = conditions;
        emit SigningCohortConditionsSet(cohortId, chainId, conditions);
    }

    function getSigningCohortConditions(
        uint32 cohortId,
        uint256 chainId
    ) external view returns (bytes memory) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(_isCohortActive(signingCohort), "Cohort not active");
        return signingCohort.conditions[chainId];
    }

    function getSigningCohortDataHash(uint32 cohortId) public view returns (bytes32) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(signingCohort.initiator != address(0), "Signing cohort not set");
        bytes32 dataHash = keccak256(abi.encode(cohortId, signingCohort.authority));
        return dataHash;
    }

    function postSigningCohortSignature(uint32 cohortId, bytes calldata signature) external {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(
            _getSigningCohortState(signingCohort) == SigningCohortState.AWAITING_SIGNATURES,
            "Not waiting for transcripts"
        );
        address provider = application.operatorToStakingProvider(msg.sender);
        require(provider != address(0), "Operator has no bond with staking provider");

        SigningCohortParticipant storage participant = _getSigner(signingCohort, provider);
        require(participant.provider != address(0), "Participant not part of signing ritual");
        require(participant.signature.length == 0, "Node already posted signature");
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        bytes32 dataHash = getSigningCohortDataHash(cohortId);
        address recovered = dataHash.toEthSignedMessageHash().recover(signature);
        require(recovered == msg.sender, "Operator signature mismatch");

        participant.operator = msg.sender;
        participant.signature = signature;
        signingCohort.totalSignatures++;

        emit SigningCohortSignaturePosted(cohortId, provider, signature);

        if (signingCohort.totalSignatures == signingCohort.numSigners) {
            _deploySigningMultisig(signingCohort.chains[0], cohortId);
        }
    }

    // TODO: not yet sure about this
    function deployAdditionalChainForSigningMultisig(
        uint256 chainId,
        uint32 cohortId
    ) external onlyRole(INITIATOR_ROLE) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(signingCohort.chains.length > 0, "Initial chain not yet deployed");
        for (uint256 i = 0; i < signingCohort.chains.length; i++) {
            require(signingCohort.chains[i] != chainId, "Already deployed");
        }
        _deploySigningMultisig(chainId, cohortId);
        signingCohort.chains.push(chainId);
    }

    function _deploySigningMultisig(uint256 _chainId, uint32 _cohortId) internal {
        SigningCohort storage signingCohort = signingCohorts[_cohortId];
        require(_isCohortActive(signingCohort), "Cohort not active");

        address[] memory _signers = new address[](signingCohort.numSigners);
        for (uint256 i = 0; i < signingCohort.signers.length; i++) {
            // ursula operator address does signing; not staking provider
            _signers[i] = signingCohort.signers[i].operator;
        }

        signingCoordinatorDispatcher.dispatch(
            _chainId,
            abi.encodeWithSelector(
                ISigningCoordinatorChild.deployCohortMultiSig.selector,
                _cohortId,
                _signers,
                signingCohort.threshold
            )
        );
        emit SigningCohortDeployed(_cohortId, _chainId);
    }

    function getSigningCohortState(
        uint32 signingCohortId
    ) public view returns (SigningCohortState) {
        return _getSigningCohortState(signingCohorts[signingCohortId]);
    }

    function _getSigningCohortState(
        SigningCohort storage _signingCohort
    ) internal view returns (SigningCohortState) {
        uint32 t0 = _signingCohort.initTimestamp;
        uint32 deadline = t0 + timeout;
        if (t0 == 0) {
            return SigningCohortState.NON_INITIATED;
        } else if (_signingCohort.totalSignatures == _signingCohort.numSigners) {
            // Cohort formation was successful
            if (block.timestamp <= _signingCohort.endTimestamp) {
                return SigningCohortState.ACTIVE;
            }
            return SigningCohortState.EXPIRED;
        } else if (block.timestamp > deadline) {
            // DKG failed due to timeout
            return SigningCohortState.TIMEOUT;
        } else if (_signingCohort.totalSignatures < _signingCohort.numSigners) {
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
