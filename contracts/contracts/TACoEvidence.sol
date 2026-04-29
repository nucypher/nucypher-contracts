// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// Assuming the use of OpenZeppelin contracts for secure cryptographic operations
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "../threshold/ITACoChildApplication.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract TACoEvidence is Ownable {
    using ECDSA for bytes32;

    // Event declarations for logging
    event CollectionStarted(
        uint32 indexed id,
        uint32 indexed startTime,
        uint32 endTime,
        uint256 nonce
    );

    event SubmissionSubmitted(
        uint32 indexed id,
        address indexed operator,
        bytes[] evidence,
        address[] peers
    );

    struct Collection {
        uint32 initTimestamp;
        uint32 endTimestamp;
        uint256 nonce;
        mapping(address => mapping(address => bool)) submissions;
    }

    ITACoChildApplication public immutable application;

    uint256 public immutable submissionWindow = 1 hours;
    Collection[] public collections;

    constructor() Ownable(msg.sender) {};

    // Function to initiate a new submission period by the admin
    function initiateCollection() public onlyOwner {
        uint32 id = uint32(collections.length);
        Collection storage collection = collections.push();
        collection.initTimestamp = uint32(block.timestamp);
        collection.endTimestamp = collection.initTimestamp + submissionWindow;
        collection.nonce =
            uint256(keccak256(abi.encodePacked(block.timestamp, block.difficulty)));
        emit CollectionStarted(
            id,
            collection.initTimestamp,
            collection.endTimestamp,
            collection.nonce
        );
    }

    // Function for nodes to submit their online status with evidence
    function submitEvidence(uint32 id, bytes[] memory signatures) public {
        address provider = application.operatorToStakingProvider(msg.sender);
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        Collection storage collection = collections[id];
        require(
            block.timestamp >= collection.initTimestamp &&
                block.timestamp <= collection.endTimestamp,
            "Submission period closed"
        );
        require(signatures.length == peers.length, "Mismatched inputs");
        emit SubmissionSubmitted(id, msg.sender, signatures, peers);

        // Verify each signature
        for (uint256 i = 0; i < signatures.length; i++) {

            bytes32 message = keccak256(abi.encodePacked(msg.sender, collection.nonce))
                .toEthSignedMessageHash();
            address signer = message.recover(signatures[i]);
            address peerProvider = application.operatorToStakingProvider(signer);
            if (application.authorizedStake(peerProvider) > 0) && (peerProvider != provider) {
                collection.submissions[msg.sender][peerProvider] = true;
            }
        }
    }
}
