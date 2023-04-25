// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";

contract StakeInfo is AccessControl {
    address public polygonChild;

    bytes32 public constant UPDATOR_ROLE = keccak256("UPDATOR_ROLE");
    mapping (address => uint8) public operatorInfo;

    constructor(address _polygonChild) {
        polygonChild = _polygonChild;
        _grantRole(UPDATOR_ROLE, polygonChild);
    }

    function setOperatorInfo(address _operator, uint8 _info) external {
        require(hasRole(UPDATOR_ROLE, msg.sender), "Caller is not the updator");
        operatorInfo[_operator] = _info;
    }
}