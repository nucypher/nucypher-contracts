// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import "../coordination/ITACoRootToChild.sol";
import "../coordination/ITACoChildToRoot.sol";
import "../coordination/TACoChildApplication.sol";
import "../TACoApplication.sol";

contract LynxMockTACoChildApplication is Ownable, ITACoChildToRoot {
    ITACoChildToRoot public immutable rootApplication;

    constructor(ITACoChildToRoot _rootApplication) {
        require(
            address(_rootApplication) != address(0),
            "Address for root application must be specified"
        );
        rootApplication = _rootApplication;
    }

    function confirmOperatorAddress(address operator) external override onlyOwner {
        rootApplication.confirmOperatorAddress(operator);
    }
}

// Goerli                  <--------->     Mumbai ....
// LynxTACoApplication                     LynxMockTACoApplication  <---> LynxTACoChildApplication
//
//
// Registry:
// ^ TACoApplication
//                                                                           ^ TACoChildApplication
contract LynxMockTACoApplication is Ownable, ITACoChildToRoot, ITACoRootToChild {
    ITACoRootToChild public childApplication;

    function setChildApplication(ITACoRootToChild _childApplication) external onlyOwner {
        childApplication = _childApplication;
    }

    function updateOperator(
        address _stakingProvider,
        address _operator
    ) external override onlyOwner {
        childApplication.updateOperator(_stakingProvider, _operator);
    }

    function updateAuthorization(
        address _stakingProvider,
        uint96 _amount
    ) external override onlyOwner {
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
