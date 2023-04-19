// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "@openzeppelin/contracts/crosschain/CrossChainEnabled.sol";
import "./IApplication.sol";

// Abstract contract. For each xchain connection we'll have a separate contract that inherits from this one.
// It will implement the isAuthorized function and read from the application contract.
abstract contract AbstractMessenger is CrossChainEnabled {
    constructor()  {}

    function isAuthorized(address operatorAddress) public view returns(bool) {
        return true;
    }

    function update() public {
    }
}