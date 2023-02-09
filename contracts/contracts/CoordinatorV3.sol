// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./proxy/Upgradeable.sol";

/**
* @title CoordinatorV1
* @notice Coordination layer for DKG-TDec
*/
contract CoordinatorV3 is Upgradeable {

    uint256 DKG_SIZE = 8;

    // DKG state signals
    event StartRitual(uint32 indexed ritualId, address[] nodes);
    event StartTranscriptRound(uint32 indexed ritualId);
    event StartAggregationRound(uint32 indexed ritualId);
    event EndRitual(uint32 indexed ritualId, RitualStatus status);

    // Node events
    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event AggregationPosted(uint32 indexed ritualId, address indexed node, address[] confirmedNodes);

    // Admin events
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
   // event DkgSizeChanged(uint32 oldSize, uint32 newSize);

    enum RitualStatus {
        WAITING_FOR_TRANSCRIPTS,
        WAITING_FOR_CONFIRMATIONS,
        COMPLETED,
        FAILED,
        FINAL
    }

    struct Rite {
        address node;
        bool aggregated;
        bytes32 transcript;
    }

    struct Ritual {
        uint32 id;
        uint32 initTimestamp;
        uint32 totalTranscripts;
        uint32 totalConfirmations;
        RitualStatus status;
        Rite[DKG_SIZE] rite;
    }

    Ritual[] public rituals;

    constructor(uint32 _timeout) {
        timeout = _timeout;
    }

    function checkActiveRitual(Ritual ritual) {
        delta = uint32(block.timestamp) - ritual.initTimestamp;
        if (delta > TIMEOUT) {
            ritual.status = RitualStatus.FAILED;
            emit Timeout(ritualId);  // penalty hook, missing nodes can be known at this stage
            emit EndRitual(ritualId, ritual.status);
            revert("Ritual timed out");
        }
    }

    function setTimeout(uint32 newTimeout) external onlyOwner {
        oldTimeout = timeout;
        timeout = newTimeout;
        emit TimeoutChanged(oldTimeout, NewTimeout);
    }

    function setDkgSize(uint32 newSize) external onlyOwner {
        oldSize = dkgSize;
        DKG_SIZE = newSize;
        emit DkgSizeChanged(oldSize, newSize);
    }

    function numberOfRituals() external view returns(uint256){
        return rituals.length;
    }

    function getRites(uint32 ritualId) external view returns(Rite[] memory){
        Rite[] memory rites = new Rite[](rituals[ritualId].rite.length);
        for(uint32 i=0; i < rituals[ritualId].rite.length; i++){
            rites[i] = rituals[ritualId].rite[i];
        }
        return rites;
    }

    function initiateRitual(address[] calldata nodes) external {
        // TODO: Check for payment
        // TODO: Check for expiration time
        // TODO: Improve DKG size choices
        require(nodes.length == DKG_SIZE, "Invalid number of nodes");

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.id = id;
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.status = RitualStatus.WAITING_FOR_TRANSCRIPTS;

        address previousNode = nodes[0];
        ritual.rite[0].node = previousNode;
        address currentNode;
        for(uint256 i=1; i < nodes.length; i++){
            currentNode = nodes[i];
            require(currentNode > previousNode, "Nodes must be sorted");
            ritual.rite[i].node = currentNode;
            previousNode = currentNode;
            // TODO: Check nodes are eligible (staking, etc)
        }

        emit StartRitual(id, nodes);
        return ritual.id;
    }

    function postTranscript(uint32 ritualId, uint256 nodeIndex, bytes calldata transcript) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.rite[nodeIndex].node == msg.sender, "Node not part of ritual");

        require(ritual.status == RitualStatus.WAITING_FOR_TRANSCRIPTS, "Not waiting for transcripts");
        require(ritual.rite[nodeIndex].transcript == bytes32(0), "Node already posted transcript");
        require(ritual.rite[nodeIndex].aggregated == false, "Node already posted aggregation");

        checkActiveRitual(ritualId);

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        ritual.rite[nodeIndex].transcript = transcriptDigest;
        emit TranscriptPosted(ritualId, msg.sender, transcriptDigest);
        ritual.totalTranscripts++;

        if (ritual.totalTranscripts == DKG_SIZE){
            ritual.status = RitualStatus.WAITING_FOR_CONFIRMATIONS;
            emit StartAggregationRound(ritualId);
        }
    }

    function postConfirmation(uint32 ritualId, uint256 nodeIndex, bytes calldata aggregatedTranscripts) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_CONFIRMATIONS, "Not waiting for confirmations");
        require(ritual.rite[nodeIndex].node == msg.sender, "Node not part of ritual");
        checkActiveRitual(ritualId);

        ritual.rite[nodeIndex].transcript = aggregatedTranscripts;
        ritual.rite[nodeIndex].aggregated = true;
        ritual.totalConfirmations++;

        if (ritual.totalConfirmations == DKG_SIZE){
            ritual.status = RitualStatus.COMPLETED;
            emit EndRitual(ritualId, ritual.status);
        }
        emit AggregationPosted(ritualId, msg.sender, confirmedNodes);
    }

    function finalizeRitual(uint32 ritualId) {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.COMPLETED, 'ritual not complete');

        prev_rite = ritual.rite[0];
        for(uint32 i=1; i < ritual.rite.length; i++){
            rite = ritual.rite[i];
            if (rite.transcript != prev_rite.transcript) {
                ritual.status = RitualStatus.FAILED;
                emit EndRitual(ritualId, ritual.status);
                revert('aggregated transcripts do not match');
            }
            prev_rite = rite;
        }

        // mark as finalized
        ritual.status = RitualStatus.FINAL;
        emit EndRitual(ritualId, ritual.status);
    }


}