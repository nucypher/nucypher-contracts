// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// Assuming the use of OpenZeppelin contracts for secure cryptographic operations
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "../threshold/ITACoChildApplication.sol";

contract TACoEvidence {
    using ECDSA for bytes32;

    // Event declarations for logging
    event CollectionStarted(
        uint32 indexed id,
        uint32 indexed startTime,
        uint32 endTime,
        uint256 nonce
    );

    struct Submission {
        address operator;
        bytes32 evidence;
    }
    struct Collection {
        uint32 initTimestamp;
        uint32 endTimestamp;
        uint256 nonce;
        mapping(address => Submission[]) submissions;
    }

    ITACoChildApplication public immutable application;

    uint256 public submissionWindow = 1 hours;
    Collection[] public collections;

    constructor() {
        admin = msg.sender;
    }

    // Modifier to restrict certain functions to the contract admin
    modifier onlyAdmin() {
        require(msg.sender == admin, "Not authorized");
        _;
    }

    // Function to initiate a new submission period by the admin
    function initiateCollection() public onlyAdmin {
        uint32 id = uint32(collections.length);
        Collection storage collection = collections.push();
        collection.initTimestamp = uint32(block.timestamp);
        collection.endTimestamp = collection.initTimestamp + submissionWindow;
        collection.nonce =
            uint256(keccak256(abi.encodePacked(block.timestamp, block.difficulty))) %
            10 ** 18;
        emit CollectionStarted(
            id,
            collection.initTimestamp,
            collection.endTimestamp,
            collection.nonce
        );
    }

    // Function for nodes to submit their online status with evidence
    function submitEvidence(uint32 id, bytes[] memory signatures, address[] memory peers) public {
        address provider = application.operatorToStakingProvider(msg.sender);
        require(application.authorizedStake(provider) > 0, "Not enough authorization");

        Collection storage collection = collections[id];
        require(
            block.timestamp >= collection.initTimestamp &&
                block.timestamp <= collection.endTimestamp,
            "Submission period closed"
        );
        require(signatures.length == peers.length, "Mismatched inputs");

        // Verify each signature
        for (uint256 i = 0; i < signatures.length; i++) {
            address peerProvider = application.operatorToStakingProvider(peers[i]);
            // is this a require?? maybe just a condition check
            require(
                application.authorizedStake(peerProvider) > 0,
                "Not enough authorization for peer evidence"
            );
            bytes32 message = keccak256(abi.encodePacked(msg.sender, collection.nonce))
                .toEthSignedMessageHash();
            address signer = message.recover(signatures[i]);
            if (signer == peers[i]) {
                collection.submissions[msg.sender].push(
                    Submission({operator: peers[i], evidence: signatures[i]})
                );
            }
        }
    }
}
