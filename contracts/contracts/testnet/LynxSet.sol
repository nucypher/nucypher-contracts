// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import "../coordination/ITACoRootToChild.sol";
import "../coordination/ITACoChildToRoot.sol";
import "../coordination/TACoChildApplication.sol";

contract LynxRootApplication is Ownable, ITACoChildToRoot {
    ITACoRootToChild public childApplication;

    function setChildApplication(ITACoRootToChild _childApplication) external onlyOwner {
        childApplication = _childApplication;
    }

    function updateOperator(address _stakingProvider, address _operator) external onlyOwner {
        childApplication.updateOperator(_stakingProvider, _operator);
    }

    function updateAuthorization(address _stakingProvider, uint96 _amount) external onlyOwner {
        childApplication.updateAuthorization(_stakingProvider, _amount);
    }

    // solhint-disable-next-line no-empty-blocks
    function confirmOperatorAddress(address _operator) external override {}
}

contract LynxTACoChildApplication is TACoChildApplication, Ownable {
    constructor(ITACoChildToRoot _rootApplication) TACoChildApplication(_rootApplication) {}

    function setCoordinator(address _coordinator) external onlyOwner {
        require(_coordinator != address(0), "Coordinator must be specified");
        require(
            address(Coordinator(_coordinator).application()) == address(this),
            "Invalid coordinator"
        );
        coordinator = _coordinator;
    }
}

contract LynxRitualToken is ERC20("LynxRitualToken", "LRT") {
    constructor(uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }
}
