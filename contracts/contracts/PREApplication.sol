// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/utils/math/SafeCast.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "../threshold/IApplication.sol";
import "../threshold/IStaking.sol";
import "./Adjudicator.sol";


/**
* @title PRE Application
* @notice Contract distributes rewards for participating in app and slashes for violating rules
*/
contract PREApplication is IApplication, Adjudicator, OwnableUpgradeable {

    using SafeERC20 for IERC20;
    using SafeCast for uint256;

    /**
    * @notice Signals that distributor role was set
    * @param distributor Address of reward distributor
    */
    event RewardDistributorSet(address indexed distributor);

    /**
    * @notice Signals that reward was added
    * @param reward Amount of reward
    */
    event RewardAdded(uint256 reward);

    /**
    * @notice Signals that the beneficiary related to the staking provider received reward
    * @param stakingProvider Staking provider address
    * @param beneficiary Beneficiary address
    * @param reward Amount of reward
    */
    event RewardPaid(address indexed stakingProvider, address indexed beneficiary, uint256 reward);

    /**
    * @notice Signals that authorization was increased for the staking provider
    * @param stakingProvider Staking provider address
    * @param fromAmount Previous amount of increased authorization
    * @param toAmount New amount of increased authorization
    */
    event AuthorizationIncreased(address indexed stakingProvider, uint96 fromAmount, uint96 toAmount);

    /**
    * @notice Signals that authorization was decreased involuntary
    * @param stakingProvider Staking provider address
    * @param fromAmount Previous amount of authorized tokens
    * @param toAmount Amount of authorized tokens to decrease
    */
    event AuthorizationInvoluntaryDecreased(address indexed stakingProvider, uint96 fromAmount, uint96 toAmount);

    /**
    * @notice Signals that authorization decrease was requested for the staking provider
    * @param stakingProvider Staking provider address
    * @param fromAmount Current amount of authorized tokens
    * @param toAmount Amount of authorization to decrease
    */
    event AuthorizationDecreaseRequested(address indexed stakingProvider, uint96 fromAmount, uint96 toAmount);

    /**
    * @notice Signals that authorization decrease was approved for the staking provider
    * @param stakingProvider Staking provider address
    * @param fromAmount Previous amount of authorized tokens
    * @param toAmount Decreased amount of authorized tokens
    */
    event AuthorizationDecreaseApproved(address indexed stakingProvider, uint96 fromAmount, uint96 toAmount);

    /**
    * @notice Signals that authorization was resynchronized
    * @param stakingProvider Staking provider address
    * @param fromAmount Previous amount of authorized tokens
    * @param toAmount Resynchronized amount of authorized tokens
    */
    event AuthorizationReSynchronized(address indexed stakingProvider, uint96 fromAmount, uint96 toAmount);

    /**
    * @notice Signals that the staking provider was slashed
    * @param stakingProvider Staking provider address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in units of T)
    */
    event Slashed(address indexed stakingProvider, uint256 penalty, address indexed investigator, uint256 reward);

    /**
    * @notice Signals that an operator was bonded to the staking provider
    * @param stakingProvider Staking provider address
    * @param operator Operator address
    * @param previousOperator Previous operator address
    * @param startTimestamp Timestamp bonding occurred
    */
    event OperatorBonded(
        address indexed stakingProvider,
        address indexed operator,
        address indexed previousOperator,
        uint256 startTimestamp
    );

    /**
    * @notice Signals that an operator address is confirmed
    * @param stakingProvider Staking provider address
    * @param operator Operator address
    */
    event OperatorConfirmed(address indexed stakingProvider, address indexed operator);

    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint64 operatorStartTimestamp;

        uint96 authorized;
        uint96 deauthorizing; // TODO real usage only in getActiveStakingProviders, maybe remove?
        uint64 endDeauthorization;

        uint96 tReward;
        uint96 rewardPerTokenPaid;
    }

    uint256 public immutable minAuthorization;
    uint256 public immutable minOperatorSeconds;
    uint256 public immutable rewardDuration;
    uint256 public immutable deauthorizationDuration;

    IStaking public immutable tStaking;
    IERC20 public immutable token;

    mapping (address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromOperator;

    address public rewardDistributor;
    uint256 public periodFinish;
    uint256 public rewardRateDecimals;
    uint256 public lastUpdateTime;
    uint96 public rewardPerTokenStored;
    uint96 public authorizedOverall;

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token T token contract
    * @param _tStaking T token staking contract
    * @param _hashAlgorithm Hashing algorithm
    * @param _basePenalty Base for the penalty calculation
    * @param _penaltyHistoryCoefficient Coefficient for calculating the penalty depending on the history
    * @param _percentagePenaltyCoefficient Coefficient for calculating the percentage penalty
    * @param _minAuthorization Amount of minimum allowable authorization
    * @param _minOperatorSeconds Min amount of seconds while an operator can't be changed
    * @param _rewardDuration Duration of one reward cycle
    * @param _deauthorizationDuration Duration of decreasing authorization
    */
    constructor(
        IERC20 _token,
        IStaking _tStaking,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient,
        uint256 _minAuthorization,
        uint256 _minOperatorSeconds,
        uint256 _rewardDuration,
        uint256 _deauthorizationDuration
    )
        Adjudicator(
            _hashAlgorithm,
            _basePenalty,
            _penaltyHistoryCoefficient,
            _percentagePenaltyCoefficient
        )
    {
        require(
            _rewardDuration != 0 &&
            _tStaking.authorizedStake(address(this), address(this)) == 0 &&
            _token.totalSupply() > 0,
            "Wrong input parameters"
        );
        rewardDuration = _rewardDuration;
        deauthorizationDuration = _deauthorizationDuration;
        minAuthorization = _minAuthorization;
        token = _token;
        tStaking = _tStaking;
        minOperatorSeconds = _minOperatorSeconds;
        _disableInitializers();
    }

    /**
    * @dev Update reward for the specified staking provider
    */
    modifier updateReward(address _stakingProvider) {
        updateRewardInternal(_stakingProvider);
        _;
    }

    /**
    * @dev Checks caller is T staking contract
    */
    modifier onlyStakingContract()
    {
        require(msg.sender == address(tStaking), "Caller must be the T staking contract");
        _;
    }

    /**
    * @dev Checks caller is a staking provider or stake owner
    */
    modifier onlyOwnerOrStakingProvider(address _stakingProvider)
    {
        require(isAuthorized(_stakingProvider), "Not owner or provider");
        if (_stakingProvider != msg.sender) {
            (address owner,,) = tStaking.rolesOf(_stakingProvider);
            require(owner == msg.sender, "Not owner or provider");
        }
        _;
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize() external initializer {
        __Ownable_init();
    }

    //------------------------Reward------------------------------

    /**
    * @notice Set reward distributor address
    */
    function setRewardDistributor(address _rewardDistributor)
        external
        onlyOwner
    {
        rewardDistributor = _rewardDistributor;
        emit RewardDistributorSet(_rewardDistributor);
    }

    /**
    * @notice Update reward for the specified staking provider
    * @param _stakingProvider Staking provider address
    */
    function updateRewardInternal(address _stakingProvider) internal {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (_stakingProvider != address(0)) {
            StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
            info.tReward = earned(_stakingProvider);
            info.rewardPerTokenPaid = rewardPerTokenStored;
        }
    }

    /**
    * @notice Returns last time when reward was applicable
    */
    function lastTimeRewardApplicable() public view returns (uint256) {
        return Math.min(block.timestamp, periodFinish);
    }

    /**
    * @notice Returns current value of reward per token
    */
    function rewardPerToken() public view returns (uint96) {
        if (authorizedOverall == 0) {
            return rewardPerTokenStored;
        }
        uint256 result = rewardPerTokenStored +
                (lastTimeRewardApplicable() - lastUpdateTime)
                * rewardRateDecimals
                / authorizedOverall;
        return result.toUint96();
    }

    /**
    * @notice Returns amount of reward for the staking provider
    * @param _stakingProvider Staking provider address
    */
    function earned(address _stakingProvider) public view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (!info.operatorConfirmed) {
            return info.tReward;
        }
        uint256 result = uint256(info.authorized) *
                (rewardPerToken() - info.rewardPerTokenPaid)
                / 1e18
                + info.tReward;
        return result.toUint96();
    }

    /**
    * @notice Transfer reward for the next period. Can be called only by distributor
    * @param _reward Amount of reward
    */
    function pushReward(uint96 _reward) external updateReward(address(0)) {
        require(msg.sender == rewardDistributor, "Only distributor can push rewards");
        require(_reward > 0, "Reward must be specified");
        if (block.timestamp >= periodFinish) {
            rewardRateDecimals = uint256(_reward) * 1e18 / rewardDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRateDecimals;
            rewardRateDecimals = (uint256(_reward) * 1e18 + leftover) / rewardDuration;
        }
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardDuration;
        emit RewardAdded(_reward);
        token.safeTransferFrom(msg.sender, address(this), _reward);
    }

    /**
    * @notice Withdraw available amount of T reward to beneficiary. Can be called only by beneficiary
    * @param _stakingProvider Staking provider address
    */
    function withdraw(address _stakingProvider) external updateReward(_stakingProvider) {
        address beneficiary = getBeneficiary(_stakingProvider);
        require(msg.sender == beneficiary, "Caller must be beneficiary");

        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.tReward > 0, "No reward to withdraw");
        uint96 value = info.tReward;
        info.tReward = 0;
        emit RewardPaid(_stakingProvider, beneficiary, value);
        token.safeTransfer(beneficiary, value);
    }

    //------------------------Authorization------------------------------
    /**
    * @notice Recalculate `authorizedOverall` if desync happened
    */
    function resynchronizeAuthorizedOverall(StakingProviderInfo storage _info, uint96 _properAmount) internal {
        if (_info.authorized != _properAmount) {
            authorizedOverall -= _info.authorized - _properAmount;
        }
    }

    /**
    * @notice Recalculate reward and save increased authorization. Can be called only by staking contract
    * @param _stakingProvider Address of staking provider
    * @param _fromAmount Amount of previously authorized tokens to PRE application by staking provider
    * @param _toAmount Amount of authorized tokens to PRE application by staking provider
    */
    function authorizationIncreased(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    )
        external override onlyStakingContract updateReward(_stakingProvider)
    {
        require(_stakingProvider != address(0) && _toAmount > 0, "Input parameters must be specified");
        require(_toAmount >= minAuthorization, "Authorization must be greater than minimum");

        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(
            _stakingProviderFromOperator[_stakingProvider] == address(0) ||
            _stakingProviderFromOperator[_stakingProvider] == _stakingProvider,
            "A provider can't be an operator for another provider"
        );

        if (info.operatorConfirmed) {
            resynchronizeAuthorizedOverall(info, _fromAmount);
            authorizedOverall += _toAmount - _fromAmount;
        }

        info.authorized = _toAmount;
        emit AuthorizationIncreased(_stakingProvider, _fromAmount, _toAmount);
    }

    /**
    * @notice Immediately decrease authorization. Can be called only by staking contract
    * @param _stakingProvider Address of staking provider
    * @param _fromAmount Previous amount of authorized tokens
    * @param _toAmount Amount of authorized tokens to decrease
    */
    function involuntaryAuthorizationDecrease(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    )
        external override onlyStakingContract updateReward(_stakingProvider)
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (info.operatorConfirmed) {
            resynchronizeAuthorizedOverall(info, _fromAmount);
            authorizedOverall -= _fromAmount - _toAmount;
        }

        info.authorized = _toAmount;
        if (info.authorized < info.deauthorizing) {
            info.deauthorizing = info.authorized;
        }
        emit AuthorizationInvoluntaryDecreased(_stakingProvider, _fromAmount, _toAmount);

        if (info.authorized == 0) {
            _stakingProviderFromOperator[info.operator] = address(0);
            info.operator = address(0);
            info.operatorConfirmed == false;
        }
    }

    /**
    * @notice Register request of decreasing authorization. Can be called only by staking contract
    * @param _stakingProvider Address of staking provider
    * @param _fromAmount Current amount of authorized tokens
    * @param _toAmount Amount of authorized tokens to decrease
    */
    function authorizationDecreaseRequested(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    )
        external override onlyStakingContract updateReward(_stakingProvider)
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(_toAmount <= info.authorized, "Amount to decrease greater than authorized");
        require(
            _toAmount == 0 || _toAmount >= minAuthorization,
            "Resulting authorization will be less than minimum"
        );
        if (info.operatorConfirmed) {
            resynchronizeAuthorizedOverall(info, _fromAmount);
        }

        info.authorized = _fromAmount;
        info.deauthorizing = _fromAmount - _toAmount;
        info.endDeauthorization = uint64(block.timestamp + deauthorizationDuration);
        emit AuthorizationDecreaseRequested(_stakingProvider, _fromAmount, _toAmount);
    }

    /**
    * @notice Approve request of decreasing authorization. Can be called by anyone
    * @param _stakingProvider Address of staking provider
    */
    function finishAuthorizationDecrease(address _stakingProvider) external updateReward(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.deauthorizing > 0, "There is no deauthorizing in process");
        require(info.endDeauthorization <= block.timestamp, "Authorization decrease has not finished yet");

        uint96 toAmount = tStaking.approveAuthorizationDecrease(_stakingProvider);

        if (info.operatorConfirmed) {
            authorizedOverall -= info.authorized - toAmount;
        }

        emit AuthorizationDecreaseApproved(_stakingProvider, info.authorized, toAmount);
        info.authorized = toAmount;
        info.deauthorizing = 0;
        info.endDeauthorization = 0;

        if (info.authorized == 0) {
            _stakingProviderFromOperator[info.operator] = address(0);
            info.operator = address(0);
            info.operatorConfirmed == false;
        }
    }

    /**
    * @notice Read authorization from staking contract and store it. Can be called by anyone
    * @param _stakingProvider Address of staking provider
    */
    function resynchronizeAuthorization(address _stakingProvider) external updateReward(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        uint96 newAuthorized = tStaking.authorizedStake(_stakingProvider, address(this));
        require(info.authorized > newAuthorized, "Nothing to synchronize");

        if (info.operatorConfirmed) {
            authorizedOverall -= info.authorized - newAuthorized;
        }
        emit AuthorizationReSynchronized(_stakingProvider, info.authorized, newAuthorized);

        info.authorized = newAuthorized;
        if (info.authorized < info.deauthorizing) {
            info.deauthorizing = info.authorized;
        }

        if (info.authorized == 0) {
            _stakingProviderFromOperator[info.operator] = address(0);
            info.operator = address(0);
            info.operatorConfirmed == false;
        }
    }

    //-------------------------Main-------------------------
    /**
    * @notice Returns staking provider for specified operator
    */
    function stakingProviderFromOperator(address _operator) public view override returns (address) {
        return _stakingProviderFromOperator[_operator];
    }

    /**
    * @notice Returns operator for specified staking provider
    */
    function getOperatorFromStakingProvider(address _stakingProvider) public view returns (address) {
        return stakingProviderInfo[_stakingProvider].operator;
    }

    /**
    * @notice Get all tokens delegated to the staking provider
    */
    function authorizedStake(address _stakingProvider) public view override returns (uint96) {
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    /**
    * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
    * @param _startIndex Start index for looking in providers array
    * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active providers
    * @return activeStakingProviders Array of providers and their authorized tokens.
    * Providers addresses stored as uint256
    * @dev Note that activeStakingProviders[0] is an array of uint256, but you want addresses.
    * Careful when used directly!
    */
    function getActiveStakingProviders(uint256 _startIndex, uint256 _maxStakingProviders)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeStakingProviders)
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
            uint256 eligibleAmount = info.authorized - info.deauthorizing;
            if (eligibleAmount < minAuthorization || !info.operatorConfirmed) {
                continue;
            }
            activeStakingProviders[resultIndex][0] = uint256(uint160(stakingProvider));
            activeStakingProviders[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeStakingProviders, resultIndex)
        }
    }

    /**
    * @notice Returns beneficiary related to the staking provider
    */
    function getBeneficiary(address _stakingProvider) public view returns (address payable beneficiary) {
        (, beneficiary,) = tStaking.rolesOf(_stakingProvider);
    }

    /**
    * @notice Returns true if staking provider has authorized stake to this application
    */
    function isAuthorized(address _stakingProvider) public view returns (bool) {
        return stakingProviderInfo[_stakingProvider].authorized > 0;
    }

    /**
    * @notice Returns true if operator has confirmed address
    */
    // TODO maybe _stakingProvider instead of _operator as input?
    function isOperatorConfirmed(address _operator) public view returns (bool) {
        address stakingProvider = _stakingProviderFromOperator[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        return info.operatorConfirmed;
    }

    /**
    * @notice Return the length of the array of staking providers
    */
    function getStakingProvidersLength() external view returns (uint256) {
        return stakingProviders.length;
    }

    /**
    * @notice Bond operator
    * @param _stakingProvider Staking provider address
    * @param _operator Operator address. Must be a real address, not a contract
    */
    function bondOperator(address _stakingProvider, address _operator)
        external onlyOwnerOrStakingProvider(_stakingProvider) updateReward(_stakingProvider)
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        address previousOperator = info.operator;
        require(_operator != previousOperator, "Specified operator is already bonded with this provider");
        // If this staker had a operator ...
        if (previousOperator != address(0)) {
            require(
                !info.operatorConfirmed ||
                block.timestamp >= uint256(info.operatorStartTimestamp) + minOperatorSeconds,
                "Not enough time passed to change operator"
            );
            // Remove the old relation "operator->stakingProvider"
            _stakingProviderFromOperator[previousOperator] = address(0);
        }

        if (_operator != address(0)) {
            require(_stakingProviderFromOperator[_operator] == address(0), "Specified operator is already in use");
            require(
                _operator == _stakingProvider || getBeneficiary(_operator) == address(0),
                "Specified operator is a provider"
            );
            // Set new operator->stakingProvider relation
            _stakingProviderFromOperator[_operator] = _stakingProvider;
        }

        if (info.operatorStartTimestamp == 0) {
            stakingProviders.push(_stakingProvider);
        }

        if (info.operatorConfirmed) {
            authorizedOverall -= info.authorized;
        }

        // Bond new operator (or unbond if _operator == address(0))
        info.operator = _operator;
        info.operatorStartTimestamp = uint64(block.timestamp);
        info.operatorConfirmed = false;
        emit OperatorBonded(_stakingProvider, _operator, previousOperator, block.timestamp);
    }

    /**
    * @notice Make a confirmation by operator
    */
    function confirmOperatorAddress() external {
        address stakingProvider = _stakingProviderFromOperator[msg.sender];
        require(isAuthorized(stakingProvider), "No stake associated with the operator");
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        require(!info.operatorConfirmed, "Operator address is already confirmed");
        require(msg.sender == tx.origin, "Only operator with real address can make a confirmation");

        updateRewardInternal(stakingProvider);
        info.operatorConfirmed = true;
        authorizedOverall += info.authorized;
        emit OperatorConfirmed(stakingProvider, msg.sender);
    }

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the provider's stake and reward the investigator
    * @param _stakingProvider Staking provider address
    * @param _penalty Penalty
    * @param _investigator Investigator
    */
    function slash(
        address _stakingProvider,
        uint96 _penalty,
        address _investigator
    )
        internal override
    {
        address[] memory stakingProviderWrapper = new address[](1);
        stakingProviderWrapper[0] = _stakingProvider;
        tStaking.seize(_penalty, 100, _investigator, stakingProviderWrapper);
    }

}
