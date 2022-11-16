// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
* @title CoordinatorV1
* @notice Coordination layer for DKG-TDec
*/
contract CoordinatorV1 {

    uint8 public constant DKG_SIZE = 8;

    event NewRitual(uint32 indexed ritualID, address[] nodes);
    event TranscriptPosted(uint32 indexed ritualID, address indexed node, bytes32 transcriptDigest);
    event ConfirmationPosted(uint32 indexed ritualID, address indexed node, address[] confirmedNodes);

    enum RitualState {
        NON_INITIATED,
        WAITING_FOR_TRANSCRIPTS,
        WAITING_FOR_CONFIRMATIONS,
        ENDED
    }

    // TODO: Find better name
    struct Performance {
        address node;
        uint96 confirmedBy;
        bytes32 transcript;
    }

    struct Ritual {
        uint32 id;
        uint32 initTimestamp;
        Performance[DKG_SIZE] performance;
    }

    uint32 public immutable transcriptsWindow;
    uint32 public immutable confirmationsWindow;
    Ritual[] public rituals;

    constructor(uint32 _transcriptsWindow, uint32 _confirmationsWindow){
        transcriptsWindow = _transcriptsWindow;
        confirmationsWindow = _confirmationsWindow;
    }

    function numberOfRituals() external view returns(uint256){
        return rituals.length;
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

        address previousNode = nodes[0];
        ritual.performance[0].node = previousNode;
        address currentNode;
        for(uint256 i=1; i < nodes.length; i++){
            currentNode = nodes[i];
            require(currentNode > previousNode, "Nodes must be sorted");
            ritual.performance[i].node = currentNode;
            previousNode = currentNode;
            // TODO: Check nodes are eligible (staking, etc)
        }

        emit NewRitual(id, nodes);
    }

    function postTranscript(uint32 ritualID, uint256 nodeIndex, bytes calldata transcript) external {
        Ritual storage ritual = rituals[ritualID];
        require(getRitualState(ritual) == RitualState.WAITING_FOR_TRANSCRIPTS, "Not waiting for transcripts");
        require(ritual.performance[nodeIndex].node == msg.sender, "Node not part of ritual");

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        ritual.performance[nodeIndex].transcript = transcriptDigest;
        
        emit TranscriptPosted(ritualID, msg.sender, transcriptDigest);
    }

    function postConfirmation(uint32 ritualID, uint256 nodeIndex, uint256[] calldata confirmedNodesIndexes) external {
        Ritual storage ritual = rituals[ritualID];
        require(getRitualState(ritual) == RitualState.WAITING_FOR_CONFIRMATIONS, "Not waiting for confirmations");
        require(
            ritual.performance[nodeIndex].node == msg.sender &&
            ritual.performance[nodeIndex].transcript != bytes32(0),
            "Node not part of ritual"
        );

        require(confirmedNodesIndexes.length <= DKG_SIZE, "Invalid number of confirmations");

        address[] memory confirmedNodes = new address[](confirmedNodesIndexes.length);
        
        // First, node adds itself to its list of confirmers
        uint96 caller = uint96(2 ** nodeIndex);
        ritual.performance[nodeIndex].confirmedBy |= caller;
        for(uint256 i=0; i < confirmedNodesIndexes.length; i++){
            uint256 confirmedNodeIndex = confirmedNodesIndexes[i];
            require(confirmedNodeIndex < DKG_SIZE, "Invalid node index");
            // We add caller to the list of confirmations of each confirmed node
            ritual.performance[confirmedNodeIndex].confirmedBy |= caller;
            confirmedNodes[i] = ritual.performance[confirmedNodeIndex].node;
        }
        emit ConfirmationPosted(ritualID, msg.sender, confirmedNodes);
    }

    function getRitualState(Ritual storage ritual) internal view returns (RitualState){
        uint32 t0 = ritual.initTimestamp;
        if(t0 == 0){
            return RitualState.NON_INITIATED;
        } else if (block.timestamp < t0 + transcriptsWindow){
            return RitualState.WAITING_FOR_TRANSCRIPTS;
        } else if (block.timestamp < t0 + transcriptsWindow + confirmationsWindow){
            return RitualState.WAITING_FOR_CONFIRMATIONS;
        } else {
            return RitualState.ENDED;
        }
    }

}