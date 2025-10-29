// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin-upgradeable/contracts/access/extensions/AccessControlDefaultAdminRulesUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./ISigningCoordinatorChild.sol";
import "./SigningCoordinatorDispatcher.sol";
import "../TACoApplication.sol";

// SigningCoordinator ----> Dispatcher ----> (Relevant) L1Sender ---------[BRIDGE]---------- L2Receiver ----> SigningCoordinatorChild (1. deploys multisig OR 2. updates multisig)

contract SigningCoordinator is Initializable, AccessControlDefaultAdminRulesUpgradeable {
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    // Signing protocol
    event InitiateSigningCohort(
        uint32 indexed cohortId,
        uint256 chainId,
        address indexed authority,
        address[] participants
    );
    event SigningCohortSignaturePosted(
        uint32 indexed cohortId,
        address indexed provider,
        address indexed signer,
        bytes signature
    );
    event SigningCohortDeployed(uint32 indexed cohortId, uint256 chainId);

    // Cohort Administration
    event SigningCohortConditionsSet(uint32 indexed cohortId, uint256 chainId, bytes conditions);

    // Protocol Administration
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
    event MaxCohortSizeChanged(uint16 oldSize, uint16 newSize);
    event DispatcherChanged(address oldDispatcher, address newDispatcher);

    struct SigningCohortParticipant {
        address provider;
        address signerAddress;
        bytes signingRequestStaticKey;
        uint256[20] gap;
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

    enum SigningCohortState {
        NON_INITIATED,
        AWAITING_SIGNATURES,
        TIMEOUT,
        ACTIVE,
        EXPIRED
    }

    TACoApplication public immutable application;
    SigningCoordinatorDispatcher public signingCoordinatorDispatcher;

    uint96 private immutable minAuthorization;

    uint32 public timeout;
    uint16 public maxCohortSize;

    uint256[20] internal __preSentinelGap;
    SigningCohortParticipant internal __sentinelSigner;
    uint256[20] internal __postSentinelGap;

    constructor(TACoApplication _application) {
        application = _application;
        minAuthorization = _application.minimumAuthorization();
        _disableInitializers();
    }

    function initialize(
        uint32 _timeout,
        uint16 _maxDkgSize,
        SigningCoordinatorDispatcher _signingCoordinatorDispatcher,
        address _admin
    ) external initializer {
        timeout = _timeout;
        maxCohortSize = _maxDkgSize;
        signingCoordinatorDispatcher = _signingCoordinatorDispatcher;
        __AccessControlDefaultAdminRules_init(0, _admin);
    }

    function setTimeout(uint32 newTimeout) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit TimeoutChanged(timeout, newTimeout);
        timeout = newTimeout;
    }

    function setMaxDkgSize(uint16 newSize) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit MaxCohortSizeChanged(maxCohortSize, newSize);
        maxCohortSize = newSize;
    }

    // TODO: this should be removed post-testing
    function setDispatcher(
        SigningCoordinatorDispatcher dispatcher
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(address(dispatcher).code.length > 0, "Dispatcher must be contract");
        emit DispatcherChanged(address(signingCoordinatorDispatcher), address(dispatcher));
        signingCoordinatorDispatcher = dispatcher;
    }

    function isCohortActive(SigningCohort storage cohort) internal view returns (bool) {
        return getSigningCohortState(cohort) == SigningCohortState.ACTIVE;
    }

    function isCohortActive(uint32 cohortId) external view returns (bool) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return isCohortActive(cohort);
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

    function getThreshold(uint32 cohortId) external view returns (uint16) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.threshold;
    }

    function getChains(uint32 cohortId) external view returns (uint256[] memory) {
        SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.chains;
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
        require(isCohortActive(signingCohort), "Cohort not active");
        require(
            signingCohort.authority == msg.sender,
            "Only the cohort authority can set conditions"
        );
        // chainId must already be deployed for the cohort
        bool chainDeployed = false;
        for (uint256 i = 0; i < signingCohort.chains.length; i++) {
            if (signingCohort.chains[i] == chainId) {
                chainDeployed = true;
                break;
            }
        }
        require(chainDeployed, "Not already deployed");

        signingCohort.conditions[chainId] = conditions;
        emit SigningCohortConditionsSet(cohortId, chainId, conditions);
    }

    function getSigningCohortConditions(
        uint32 cohortId,
        uint256 chainId
    ) external view returns (bytes memory) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        return signingCohort.conditions[chainId];
    }

    function getSigningCohortDataHash(
        uint32 cohortId,
        address operator
    ) public view returns (bytes32) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(signingCohort.initiator != address(0), "Signing cohort not set");
        bytes32 dataHash = keccak256(abi.encode(cohortId, signingCohort.authority, operator));
        return dataHash;
    }

    function postSigningCohortData(
        uint32 cohortId,
        bytes calldata signature,
        bytes calldata signingRequestStaticKey
    ) external {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(
            getSigningCohortState(signingCohort) == SigningCohortState.AWAITING_SIGNATURES,
            "Not waiting for transcripts"
        );
        address provider = application.operatorToStakingProvider(msg.sender);
        require(provider != address(0), "Operator has no bond with staking provider");

        SigningCohortParticipant storage participant = getSigner(signingCohort, provider);
        require(participant.provider != address(0), "Participant not part of signing ritual");
        require(participant.signerAddress == address(0), "Node already posted signature");
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        bytes32 dataHash = getSigningCohortDataHash(cohortId, msg.sender);
        address signerAddress = dataHash.toEthSignedMessageHash().recover(signature);

        participant.signerAddress = signerAddress;
        signingCohort.totalSignatures++;

        require(
            participant.signingRequestStaticKey.length == 0,
            "Node already provided signing request static key"
        );
        require(
            signingRequestStaticKey.length == 42,
            "Invalid length for signing request static key"
        );
        participant.signingRequestStaticKey = signingRequestStaticKey;

        emit SigningCohortSignaturePosted(cohortId, provider, signerAddress, signature);

        if (signingCohort.totalSignatures == signingCohort.numSigners) {
            deploySigningMultisig(signingCohort.chains[0], cohortId);
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
        deploySigningMultisig(chainId, cohortId);
        signingCohort.chains.push(chainId);
    }

    function deploySigningMultisig(uint256 chainId, uint32 cohortId) internal {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        require(isCohortActive(signingCohort), "Cohort not active");

        address[] memory _signers = new address[](signingCohort.numSigners);
        for (uint256 i = 0; i < signingCohort.signers.length; i++) {
            // ursula operator address does signing; not staking provider
            _signers[i] = signingCohort.signers[i].signerAddress;
        }

        signingCoordinatorDispatcher.dispatch(
            chainId,
            abi.encodeWithSelector(
                ISigningCoordinatorChild.deployCohortMultiSig.selector,
                cohortId,
                _signers,
                signingCohort.threshold
            )
        );
        emit SigningCohortDeployed(cohortId, chainId);
    }

    function getSigningCohortState(uint32 cohortId) public view returns (SigningCohortState) {
        return getSigningCohortState(signingCohorts[cohortId]);
    }

    function getSigningCohortState(
        SigningCohort storage signingCohort
    ) internal view returns (SigningCohortState) {
        uint32 t0 = signingCohort.initTimestamp;
        uint32 deadline = t0 + timeout;
        if (t0 == 0) {
            return SigningCohortState.NON_INITIATED;
        } else if (signingCohort.totalSignatures == signingCohort.numSigners) {
            // Cohort formation was successful
            if (block.timestamp <= signingCohort.endTimestamp) {
                return SigningCohortState.ACTIVE;
            }
            return SigningCohortState.EXPIRED;
        } else if (block.timestamp > deadline) {
            // DKG failed due to timeout
            return SigningCohortState.TIMEOUT;
        } else if (signingCohort.totalSignatures < signingCohort.numSigners) {
            return SigningCohortState.AWAITING_SIGNATURES;
        } else {
            /**
             * It shouldn't be possible to reach this state
             */
            revert("Ambiguous signing ritual state");
        }
    }

    function getSigningCoordinatorChild(uint256 chainId) external view returns (address) {
        address child = signingCoordinatorDispatcher.getSigningCoordinatorChild(chainId);
        return child;
    }

    function extendSigningCohortDuration(
        uint32 cohortId,
        uint32 additionalDuration
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        SigningCohort storage signingCohort = signingCohorts[cohortId];
        // TODO: while it's good to check if the cohort is active, it is
        // not necessary at the moment
        // require(isCohortActive(signingCohort), "Cohort not active");
        require(additionalDuration > 0, "Invalid duration");
        uint32 newEndTimestamp = signingCohort.endTimestamp + additionalDuration;
        signingCohort.endTimestamp = newEndTimestamp;
    }
}
