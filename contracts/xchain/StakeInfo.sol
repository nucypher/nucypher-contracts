// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract StakeInfo is AccessControl, Ownable {
    address public polygonChild;

    bytes32 public constant UPDATOR_ROLE = keccak256("UPDATOR_ROLE");
    mapping (address => uint8) public operatorInfo;

    constructor(address _polygonChild) {
        polygonChild = _polygonChild;
        _grantRole(UPDATOR_ROLE, polygonChild);
    }

    function updateOperatorInfo(address _operator, uint8 _info) external {
        require(hasRole(UPDATOR_ROLE, msg.sender), "Caller is not the updator");
        operatorInfo[_operator] = _info;
    }

    function batchUpdateOperatorInfo(address[] calldata _operators, uint8[] calldata _infos) external {
        require(hasRole(UPDATOR_ROLE, msg.sender), "Caller is not the updator");
        require(_operators.length == _infos.length, "Invalid input length");
        for (uint256 i = 0; i < _operators.length; i++) {
            operatorInfo[_operators[i]] = _infos[i];
        }
    }
}