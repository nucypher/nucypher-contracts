// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import "../coordination/TACoChildApplication.sol";

contract TapirTACoChildApplication is TACoChildApplication, Ownable {
    constructor(
        ITACoChildToRoot _rootApplication,
        uint96 _minimumAuthorization
    ) TACoChildApplication(_rootApplication, _minimumAuthorization) Ownable(msg.sender) {}

    function setCoordinator(address _coordinator) external onlyOwner {
        require(_coordinator != address(0), "Coordinator must be specified");
        require(
            address(Coordinator(_coordinator).application()) == address(this),
            "Invalid coordinator"
        );
        coordinator = _coordinator;
    }
}

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
