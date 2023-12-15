// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @notice Token for testing
 */
contract TestToken is ERC20("Test", "TT") {
    constructor(uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }

    function mint(address account, uint256 value) external {
        _mint(account, value);
    }

    function burn(address account, uint256 value) external {
        _burn(account, value);
    }
}
