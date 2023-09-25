// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import "../coordination/ITACoRootToChild.sol";
import "../coordination/ITACoChildToRoot.sol";
import "../coordination/TACoChildApplication.sol";

contract LynxRootApplication is Ownable, ITACoChildToRoot {
    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint64 operatorStartTimestamp;
        uint96 authorized;
    }

    uint96 public immutable minimumAuthorization = 40000000000000000000000;
    uint256 public immutable minOperatorSeconds = 3600;
    ITACoRootToChild public childApplication;
    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromOperator;

    function setChildApplication(ITACoRootToChild _childApplication) external onlyOwner {
        childApplication = _childApplication;
    }

    function updateAuthorization(address _stakingProvider, uint96 _amount) external onlyOwner {
        if (address(childApplication) != address(0)) {
            childApplication.updateAuthorization(_stakingProvider, _amount);
        }
    }

    function confirmOperatorAddress(address _operator) external override {
        address stakingProvider = _stakingProviderFromOperator[_operator];
        if (stakingProvider == address(0)) {
            return;
        }
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        if (!info.operatorConfirmed) {
            info.operatorConfirmed = true;
        }
    }

    //
    // Required TACoApplication functions
    //
    function stakingProviderFromOperator(address _operator) public view returns (address) {
        return _stakingProviderFromOperator[_operator];
    }

    function getOperatorFromStakingProvider(
        address _stakingProvider
    ) public view returns (address) {
        return stakingProviderInfo[_stakingProvider].operator;
    }

    function getActiveStakingProviders(
        uint256 _startIndex,
        uint256 _maxStakingProviders
    )
        external
        view
        returns (uint256 allAuthorizedTokens, uint256[2][] memory activeStakingProviders)
    {
        uint256 endIndex = stakingProviders.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxStakingProviders != 0 && _startIndex + _maxStakingProviders < endIndex) {
            endIndex = _startIndex + _maxStakingProviders;
        }
        activeStakingProviders = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address stakingProvider = stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            uint256 eligibleAmount = info.authorized;
            activeStakingProviders[resultIndex][0] = uint256(uint160(stakingProvider));
            activeStakingProviders[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeStakingProviders, resultIndex)
        }
    }

    function isAuthorized(address _stakingProvider) public view returns (bool) {
        return stakingProviderInfo[_stakingProvider].authorized > 0;
    }

    function authorizedStake(address _stakingProvider) public view returns (uint96) {
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    function isOperatorConfirmed(address _operator) public view returns (bool) {
        address stakingProvider = _stakingProviderFromOperator[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        return info.operatorConfirmed;
    }

    function getStakingProvidersLength() external view returns (uint256) {
        return stakingProviders.length;
    }

    function bondOperator(address _stakingProvider, address _operator) external onlyOwner {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        address previousOperator = info.operator;
        require(
            _operator != previousOperator,
            "Specified operator is already bonded with this provider"
        );
        // If this staker had a operator ...
        if (previousOperator != address(0)) {
            // Remove the old relation "operator->stakingProvider"
            _stakingProviderFromOperator[previousOperator] = address(0);
        }

        if (_operator != address(0)) {
            require(
                _stakingProviderFromOperator[_operator] == address(0),
                "Specified operator is already in use"
            );
            // Set new operator->stakingProvider relation
            _stakingProviderFromOperator[_operator] = _stakingProvider;
        }

        if (info.operatorStartTimestamp == 0) {
            stakingProviders.push(_stakingProvider);
        }

        // Bond new operator (or unbond if _operator == address(0))
        info.operator = _operator;
        info.operatorStartTimestamp = uint64(block.timestamp);
        info.operatorConfirmed = false;
        if (address(childApplication) != address(0)) {
            childApplication.updateOperator(_stakingProvider, _operator);
        }
    }

    //
    // Remaining IApplication functions
    //

    // solhint-disable-next-line no-empty-blocks
    function withdrawRewards(address stakingProvider) external {}

    function authorizationIncreased(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount // solhint-disable-next-line no-empty-blocks
    ) external {}

    function authorizationDecreaseRequested(
        address stakingProvider,
        uint96 fromAmount,
        uint96 toAmount // solhint-disable-next-line no-empty-blocks
    ) external {}

    function involuntaryAuthorizationDecrease(
        address stakingProvider,
        uint96 fromAmount,
        uint96 toAmount // solhint-disable-next-line no-empty-blocks
    ) external {}

    // solhint-disable-next-line no-unused-vars
    function availableRewards(address stakingProvider) external view returns (uint96) {
        return 0;
    }
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
