// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./lib/ReEncryptionValidator.sol";
import "./lib/SignatureVerifier.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/utils/math/SafeCast.sol";
import "./TACoApplication.sol";

/**
 * @title Adjudicator
 * @notice Supervises operators' behavior and punishes when something's wrong.
 * @dev |v3.1.1|
 */
contract Adjudicator {
    using UmbralDeserializer for bytes;
    using SafeCast for uint256;

    event CFragEvaluated(
        bytes32 indexed evaluationHash,
        address indexed investigator,
        bool correctness
    );
    event IncorrectCFragVerdict(
        bytes32 indexed evaluationHash,
        address indexed operator,
        address indexed stakingProvider
    );

    SignatureVerifier.HashAlgorithm public immutable hashAlgorithm;
    uint256 public immutable basePenalty;
    uint256 public immutable penaltyHistoryCoefficient;
    uint256 public immutable percentagePenaltyCoefficient;
    TACoApplication public immutable application;

    mapping(address => uint256) public penaltyHistory;
    mapping(bytes32 => bool) public evaluatedCFrags;

    /**
     * @param _hashAlgorithm Hashing algorithm
     * @param _basePenalty Base for the penalty calculation
     * @param _penaltyHistoryCoefficient Coefficient for calculating the penalty depending on the history
     * @param _percentagePenaltyCoefficient Coefficient for calculating the percentage penalty
     */
    constructor(
        TACoApplication _application,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient
    ) {
        require(
            _percentagePenaltyCoefficient != 0 && address(_application.token()) != address(0),
            "Wrong input parameters"
        );
        hashAlgorithm = _hashAlgorithm;
        basePenalty = _basePenalty;
        percentagePenaltyCoefficient = _percentagePenaltyCoefficient;
        penaltyHistoryCoefficient = _penaltyHistoryCoefficient;
        application = _application;
    }

    /**
     * @notice Submit proof that a operator created wrong CFrag
     * @param _capsuleBytes Serialized capsule
     * @param _cFragBytes Serialized CFrag
     * @param _cFragSignature Signature of CFrag by operator
     * @param _taskSignature Signature of task specification by Bob
     * @param _requesterPublicKey Bob's signing public key, also known as "stamp"
     * @param _operatorPublicKey Operator's signing public key, also known as "stamp"
     * @param _operatorIdentityEvidence Signature of operator's public key by operator's eth-key
     * @param _preComputedData Additional pre-computed data for CFrag correctness verification
     */
    function evaluateCFrag(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes,
        bytes memory _cFragSignature,
        bytes memory _taskSignature,
        bytes memory _requesterPublicKey,
        bytes memory _operatorPublicKey,
        bytes memory _operatorIdentityEvidence,
        bytes memory _preComputedData
    ) public {
        // 1. Check that CFrag is not evaluated yet
        bytes32 evaluationHash = SignatureVerifier.hash(
            abi.encodePacked(_capsuleBytes, _cFragBytes),
            hashAlgorithm
        );
        require(!evaluatedCFrags[evaluationHash], "This CFrag has already been evaluated.");
        evaluatedCFrags[evaluationHash] = true;

        // 2. Verify correctness of re-encryption
        bool cFragIsCorrect = ReEncryptionValidator.validateCFrag(
            _capsuleBytes,
            _cFragBytes,
            _preComputedData
        );
        emit CFragEvaluated(evaluationHash, msg.sender, cFragIsCorrect);

        // 3. Verify associated public keys and signatures
        require(
            ReEncryptionValidator.checkSerializedCoordinates(_operatorPublicKey),
            "Staker's public key is invalid"
        );
        require(
            ReEncryptionValidator.checkSerializedCoordinates(_requesterPublicKey),
            "Requester's public key is invalid"
        );

        UmbralDeserializer.PreComputedData memory precomp = _preComputedData.toPreComputedData();

        // Verify operator's signature of CFrag
        require(
            SignatureVerifier.verify(
                _cFragBytes,
                abi.encodePacked(_cFragSignature, precomp.lostBytes[1]),
                _operatorPublicKey,
                hashAlgorithm
            ),
            "CFrag signature is invalid"
        );

        // Verify operator's signature of taskSignature and that it corresponds to cfrag.proof.metadata
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        require(
            SignatureVerifier.verify(
                _taskSignature,
                abi.encodePacked(cFrag.proof.metadata, precomp.lostBytes[2]),
                _operatorPublicKey,
                hashAlgorithm
            ),
            "Task signature is invalid"
        );

        // Verify that _taskSignature is bob's signature of the task specification.
        // A task specification is: capsule + ursula pubkey + alice address + blockhash
        bytes32 stampXCoord;
        assembly {
            stampXCoord := mload(add(_operatorPublicKey, 32))
        }
        bytes memory stamp = abi.encodePacked(precomp.lostBytes[4], stampXCoord);

        require(
            SignatureVerifier.verify(
                abi.encodePacked(
                    _capsuleBytes,
                    stamp,
                    _operatorIdentityEvidence,
                    precomp.alicesKeyAsAddress,
                    bytes32(0)
                ),
                abi.encodePacked(_taskSignature, precomp.lostBytes[3]),
                _requesterPublicKey,
                hashAlgorithm
            ),
            "Specification signature is invalid"
        );

        // 4. Extract operator address from stamp signature.
        address operator = SignatureVerifier.recover(
            SignatureVerifier.hashEIP191(stamp, bytes1(0x45)), // Currently, we use version E (0x45) of EIP191 signatures
            _operatorIdentityEvidence
        );
        address stakingProvider = application.operatorToStakingProvider(operator);
        require(stakingProvider != address(0), "Operator must be associated with a provider");

        // 5. Check that staking provider can be slashed
        uint96 stakingProviderValue = application.authorizedStake(stakingProvider);
        require(stakingProviderValue > 0, "Provider has no tokens");

        // 6. If CFrag was incorrect, slash staking provider
        if (!cFragIsCorrect) {
            uint96 penalty = calculatePenalty(stakingProvider, stakingProviderValue);
            application.slash(stakingProvider, penalty, msg.sender);
            emit IncorrectCFragVerdict(evaluationHash, operator, stakingProvider);
        }
    }

    /**
     * @notice Calculate penalty to the staking provider
     * @param _stakingProvider Staking provider address
     * @param _stakingProviderValue Amount of tokens that belong to the staking provider
     */
    function calculatePenalty(
        address _stakingProvider,
        uint96 _stakingProviderValue
    ) internal returns (uint96) {
        uint256 penalty = basePenalty +
            penaltyHistoryCoefficient *
            penaltyHistory[_stakingProvider];
        penalty = Math.min(penalty, _stakingProviderValue / percentagePenaltyCoefficient);
        // TODO add maximum condition or other overflow protection or other penalty condition (#305?)
        penaltyHistory[_stakingProvider] = penaltyHistory[_stakingProvider] + 1;
        return penalty.toUint96();
    }
}
