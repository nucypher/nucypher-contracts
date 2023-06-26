// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "../contracts/PREApplication.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";


/**
* @notice Contract for testing PRE application contract
*/
contract TToken is ERC20("T", "T") {

    constructor (uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }

}


/**
* @notice Contract for testing PRE application contract
*/
contract ThresholdStakingForPREApplicationMock {

    struct StakingProviderInfo {
        address owner;
        address payable beneficiary;
        address authorizer;
        uint96 authorized;
        uint96 decreaseRequestTo;
    }

    PREApplication public preApplication;

    mapping (address => StakingProviderInfo) public stakingProviderInfo;

    uint96 public amountToSeize;
    uint256 public rewardMultiplier;
    address public notifier;
    address[] public stakingProvidersToSeize;

    function setApplication(PREApplication _preApplication) external {
        preApplication = _preApplication;
    }

    function stakedNu(address) external view returns (uint256) {
        return 0;
    }

    function setRoles(
        address _stakingProvider,
        address _owner,
        address payable _beneficiary,
        address _authorizer
    )
        public
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.owner = _owner;
        info.beneficiary = _beneficiary;
        info.authorizer = _authorizer;
    }

    /**
    * @dev If the function is called with only the _stakingProvider parameter,
    * we presume that the caller wants that address set for the other roles as well.
    */
    function setRoles(address _stakingProvider) external {
        setRoles(_stakingProvider, _stakingProvider, payable(_stakingProvider), _stakingProvider);
    }

    function setAuthorized(address _stakingProvider, uint96 _authorized) external {
        stakingProviderInfo[_stakingProvider].authorized = _authorized;
    }

    function setDecreaseRequest(address _stakingProvider, uint96 _decreaseRequestTo) external {
        stakingProviderInfo[_stakingProvider].decreaseRequestTo = _decreaseRequestTo;
    }

    function authorizedStake(address _stakingProvider, address _application) external view returns (uint96) {
        require(_stakingProvider == _application || _application == address(preApplication));
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    function rolesOf(address _stakingProvider) external view returns (
        address owner,
        address payable beneficiary,
        address authorizer
    ) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        owner = info.owner;
        beneficiary = info.beneficiary;
        authorizer = info.authorizer;
    }

    function approveAuthorizationDecrease(address _stakingProvider) external returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.authorized = info.decreaseRequestTo;
        return info.authorized;
    }

    function seize(
        uint96 _amount,
        uint256 _rewardMultiplier,
        address _notifier,
        address[] memory _stakingProviders
    ) external {
        amountToSeize = _amount;
        rewardMultiplier = _rewardMultiplier;
        notifier = _notifier;
        stakingProvidersToSeize = _stakingProviders;
    }

    function getLengthOfStakingProvidersToSeize() external view returns (uint256) {
        return stakingProvidersToSeize.length;
    }

    function authorizationIncreased(address _stakingProvider, uint96 _fromAmount, uint96 _toAmount) external {
        preApplication.authorizationIncreased(_stakingProvider, _fromAmount, _toAmount);
        stakingProviderInfo[_stakingProvider].authorized = _toAmount;
    }

    function involuntaryAuthorizationDecrease(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    )
        external
    {
        preApplication.involuntaryAuthorizationDecrease(_stakingProvider, _fromAmount, _toAmount);
        stakingProviderInfo[_stakingProvider].authorized = _toAmount;
    }

    function authorizationDecreaseRequested(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    )
        external
    {
        preApplication.authorizationDecreaseRequested(_stakingProvider, _fromAmount, _toAmount);
        stakingProviderInfo[_stakingProvider].decreaseRequestTo = _toAmount;
    }

}


/**
* @notice Intermediary contract for testing operator
*/
contract Intermediary {

    PREApplication immutable public preApplication;

    constructor(PREApplication _preApplication) {
        preApplication = _preApplication;
    }

    function bondOperator(address _operator) external {
        preApplication.bondOperator(address(this), _operator);
    }

    function confirmOperatorAddress() external {
        preApplication.confirmOperatorAddress();
    }

}


/**
* @notice Extended contract
*/
contract ExtendedPREApplication is PREApplication {

    constructor(
        IERC20 _token,
        IStaking _tStaking,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient,
        uint256 _minAuthorization,
        uint256 _minWorkerSeconds,
        uint256 _rewardDuration,
        uint256 _deauthorizationDuration
    )
        PREApplication(
            _token,
            _tStaking,
            _hashAlgorithm,
            _basePenalty,
            _penaltyHistoryCoefficient,
            _percentagePenaltyCoefficient,
            _minAuthorization,
            _minWorkerSeconds,
            _rewardDuration,
            _deauthorizationDuration
        )
    {}

    function testSlash(
        address _stakingProvider,
        uint96 _penalty,
        address _investigator
    ) external {
        slash(_stakingProvider, _penalty, _investigator);
    }

}
