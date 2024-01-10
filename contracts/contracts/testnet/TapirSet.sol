// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract TapirRitualToken is ERC20("TapirRitualToken", "TRT") {
    constructor(uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }
}

contract TapirStakingToken is ERC20("TapirStakingToken", "TST") {
    constructor(uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }
}
