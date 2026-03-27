// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "../TACoApplication.sol";

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

contract TapirTACoApplication is TACoApplication {
    constructor(
        IERC20 _token,
        uint96 _minimumAuthorization,
        uint256 _minOperatorSeconds
    ) TACoApplication(_token, _minimumAuthorization, _minOperatorSeconds) {}

    /**
     * Admin function to set information for a stake in testnet
     */
    function adminSetExistingStake(
        address _stakingProvider,
        address _owner,
        address _beneficiary
    ) external onlyOwner {
        require(
            _stakingProvider != address(0) && _owner != address(0) && _beneficiary != address(0),
            "Parameters are empty"
        );
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(
            _stakingProviderFromOperator[_stakingProvider] == address(0),
            "Staker is an operator"
        );

        info.owner = _owner;
        info.beneficiary = _beneficiary;
        info.authorized = minimumAuthorization;
        info.stakeless = false;
        emit Staked(_stakingProvider, _owner, _beneficiary, info.authorized);
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * Admin function to set a existing stake in testnet as stakeless
     */
    function adminSetToStakeless(address _stakingProvider) external onlyOwner {
        require(_stakingProvider != address(0), "Parameters are empty");
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];

        info.beneficiary = address(0);
        info.authorized = minimumAuthorization;
        info.stakeless = true;
        _updateAuthorization(_stakingProvider, info);
    }
}
