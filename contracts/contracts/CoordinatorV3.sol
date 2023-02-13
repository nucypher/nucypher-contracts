// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
* @title CoordinatorV1
* @notice Coordination layer for DKG-TDec
*/
contract CoordinatorV1 is Ownable {

    // Ritual
    event StartRitual(uint32 indexed ritualId, address indexed initiator, address[] nodes);
    event StartTranscriptRound(uint32 indexed ritualId);
    event StartAggregationRound(uint32 indexed ritualId);
    // TODO: Do we want the public key here? If so, we want 2 events or do we reuse this event?
    event EndRitual(uint32 indexed ritualId, address indexed initiator, RitualStatus status);

    // Node
    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event AggregationPosted(uint32 indexed ritualId, address indexed node, bytes32 aggregatedTranscriptDigest);

    // Admin
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
    event MaxDkgSizeChanged(uint32 oldSize, uint32 newSize);

    enum RitualStatus {
        NON_INITIATED,
        AWAITING_TRANSCRIPTS,
        AWAITING_AGGREGATIONS,
        TIMEOUT,
        INVALID,
        FINALIZED
    }

    uint256 public constant PUBLIC_KEY_SIZE = 48;

    struct Participant {
        address node;
        bool aggregated;
        bytes transcript;  // TODO: Consider event processing complexity vs storage cost
    }

    // TODO: Optimize layout
    struct Ritual {
        uint32 id;
        address initiator;
        uint32 dkgSize;
        uint32 threshold;
        uint32 initTimestamp;
        uint32 totalTranscripts;
        uint32 totalAggregations;
        bytes1[PUBLIC_KEY_SIZE] publicKey;
        bytes32 aggregatedTranscriptHash;
        bool aggregationMismatch;
        bytes aggregatedTranscript;
        Participant[] participant;
    }

    Ritual[] public rituals;

    uint32 public timeout;
    uint32 public maxDkgSize;

    constructor(uint32 _timeout, uint32 _maxDkgSize) {
        timeout = _timeout;
        maxDkgSize = _maxDkgSize;
    }

    function getRitualState(uint256 ritualID) external view returns (RitualState){
        // TODO: restrict to ritualID < rituals.length?
        return getRitualState(rituals[ritualId]);
    }

    function getRitualState(Ritual storage ritual) internal view returns (RitualState){
        uint32 t0 = ritual.initTimestamp;
        uint32 deadline = t0 + timeout;
        if(t0 == 0){
            return RitualState.NON_INITIATED;
        } else if (ritual.publicKey != 0x0){ // TODO: Improve check
            return RitualState.FINALIZED;
        } else if (!ritual.aggregationMismatch){
            return RitualState.INVALID;
        } else if (block.timestamp > deadline){
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
        }
    }

    function setTimeout(uint32 newTimeout) external onlyOwner {
        uint32 oldTimeout = timeout;
        timeout = newTimeout;
        emit TimeoutChanged(oldTimeout, newTimeout);
    }

    function setMaxDkgSize(uint32 newSize) external onlyOwner {
        uint32 oldSize = maxDkgSize;
        maxDkgSize = newSize;
        emit MaxDkgSizeChanged(oldSize, newSize);
    }

    function numberOfRituals() external view returns(uint256) {
        return rituals.length;
    }

    function getParticipants(uint32 ritualId) external view returns(Participant[] memory) {
        Ritual storage ritual = rituals[ritualId];
        Participant[] memory participants = new Participant[](
            ritual.participant.length
        );
        for(uint32 i=0; i < ritual.participant.length; i++){
            participants[i] = ritual.participant[i];
        }
        return participants;
    }

    function initiateRitual(address[] calldata nodes) external returns (uint32) {
        // TODO: Validate service fees, expiration dates, threshold
        require(nodes.length <= maxDkgSize, "Invalid number of nodes");

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.id = id;  // TODO: Possibly redundant
        ritual.initiator = msg.sender;  // TODO: Consider sponsor model
        ritual.threshold = threshold;  // TODO?
        ritual.dkgSize = uint32(nodes.length);
        ritual.initTimestamp = uint32(block.timestamp);

        address previousNode = nodes[0];
        ritual.participant[0].node = previousNode;
        address currentNode;
        for(uint256 i=1; i < nodes.length; i++){
            currentNode = nodes[i];
            ritual.participant[i].node = currentNode;
            previousNode = currentNode;
            // TODO: Check nodes are eligible (staking, etc)
        }

        emit StartRitual(id, msg.sender, nodes);
        emit StartTranscriptRound(id);
        return ritual.id;
    }

    function postTranscript(uint32 ritualId, uint256 nodeIndex, bytes calldata transcript) external {
        Ritual storage ritual = rituals[ritualId];
        require(
            getRitualStatus(ritual) == RitualStatus.AWAITING_TRANSCRIPTS,
            "Not waiting for transcripts"
        );
        require(
            ritual.participant[nodeIndex].node == msg.sender,
            "Node not part of ritual"
        );
        require(
            ritual.participant[nodeIndex].transcript.length == 0,
            "Node already posted transcript"
        );

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        ritual.participant[nodeIndex].transcript = transcript;  // TODO: ???
        emit TranscriptPosted(ritualId, msg.sender, transcriptDigest);
        ritual.totalTranscripts++;

        // end round
        if (ritual.totalTranscripts == ritual.dkgSize){
            emit StartAggregationRound(ritualId);
        }
    }

    function postAggregation(uint32 ritualId, uint256 nodeIndex, bytes calldata aggregatedTranscript) external {
        Ritual storage ritual = rituals[ritualId];
        require(
            getRitualStatus(ritual) == RitualStatus.AWAITING_AGGREGATIONS,
            "Not waiting for aggregations"
        );
        require(
            ritual.participant[nodeIndex].node == msg.sender,
            "Node not part of ritual"
        );
        require(
            !ritual.participant[nodeIndex].aggregated,
            "Node already posted aggregation"
        );

        // nodes commit to their aggregation result
        bytes32 aggregatedTranscriptDigest = keccak256(aggregatedTranscript);
        ritual.participant[nodeIndex].aggregated = true;
        emit AggregationPosted(ritualId, msg.sender, aggregatedTranscript);
        
        if (ritual.aggregatedTranscriptHash != aggregatedTranscriptDigest){
            ritual.aggregationMismatch = true;
            emit EndRitual(ritualId, ritual.initiator, RitualStatus.INVALID);
            // TODO: Invalid ritual
            // TODO: Consider freeing ritual storage
            return;
        }
        
        ritual.totalAggregations++;
        
        // end round - Last node posting aggregation will finalize 
        if (ritual.totalAggregations == ritual.dkgSize){
            emit EndRitual(ritualId, ritual.initiator, RitualStatus.FINALIZED);
            // TODO: Last node extracts public key bytes from aggregated transcript
            // and store in ritual.publicKey
        }
    }
}
