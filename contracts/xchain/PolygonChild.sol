// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@fx-portal/contracts/tunnel/FxBaseChildTunnel.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PolygonChild is FxBaseChildTunnel, Ownable {
    address public stakeInfoAddress;
    
    constructor(address _fxChild) FxBaseChildTunnel(_fxChild) {}

    function _processMessageFromRoot(
        uint256 /* stateId */,
        address sender,
        bytes memory data
    ) internal override validateSender(sender) {
        (bool success, /* returnId */ ) = stakeInfoAddress.call(data);
    }

    function sendMessageToRoot(bytes memory message) public {
        _sendMessageToRoot(message);
    }

    function setStakeInfoAddress(address _stakeInfoAddress) public onlyOwner {
        stakeInfoAddress = _stakeInfoAddress;
    }
}