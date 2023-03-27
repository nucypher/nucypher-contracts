// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
* @title BulletinBoard
* @notice BulletinBoard
*/
contract BulletinBoard {

    event DataPosted(bytes32 indexed digest, address indexed sender);

    mapping(bytes32 => bytes) public message;
    mapping(bytes32 => address) public sender;

    function postData(bytes calldata _data, bool _recordSender) public {
        // TODO: Use SHA256? Possibly parametrize hash function
        bytes32 digest = keccak256(_data);
        message[digest] = _data;
        emit DataPosted(digest, msg.sender);

        if(_recordSender){
            sender[digest] = msg.sender;
        }
    }

    function postData(bytes calldata _data) external {
        postData(_data, false);
    }
}
