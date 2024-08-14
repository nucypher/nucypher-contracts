// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title FreeFeeModel
 * @notice Free FeeModel
 */
contract FreeFeeModel is Ownable {
    mapping(address initiator => bool approved) public initiatorWhiteList;

    constructor() Ownable(msg.sender) {}

    function approveInitiator(address initiator) external onlyOwner {
        initiatorWhiteList[initiator] = true;
    }

    function processRitualPayment(address initiator, uint32, uint256, uint32) external {
        require(initiatorWhiteList[initiator], "Initiator not approved");
    }

    function processRitualExtending(address initiator, uint32, uint256, uint32) external {
        require(initiatorWhiteList[initiator], "Initiator not approved");
    }

    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) external {
        // solhint-disable-previous-line no-empty-blocks
    }

    function beforeIsAuthorized(uint32 ritualId) external view {
        // solhint-disable-previous-line no-empty-blocks
    }
}
