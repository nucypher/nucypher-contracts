// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/utils/math/SafeCast.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "../threshold/IApplicationWithOperator.sol";
import "../threshold/IApplicationWithDecreaseDelay.sol";
import "@threshold/contracts/staking/IStaking.sol";
import "./coordination/ITACoRootToChild.sol";
import "./coordination/ITACoChildToRoot.sol";

/**
 * @title TACo Application
 * @notice Contract distributes rewards for participating in app and slashes for violating rules
 */
contract TACoApplication is
    IApplicationWithDecreaseDelay,
    IApplicationWithOperator,
    ITACoChildToRoot,
    OwnableUpgradeable
{
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
    event AuthorizationIncreased(
        address indexed stakingProvider,
        uint96 fromAmount,
        uint96 toAmount
    );

    /**
     * @notice Signals that authorization was decreased involuntary
     * @param stakingProvider Staking provider address
     * @param fromAmount Previous amount of authorized tokens
     * @param toAmount Amount of authorized tokens to decrease
     */
    event AuthorizationInvoluntaryDecreased(
        address indexed stakingProvider,
        uint96 fromAmount,
        uint96 toAmount
    );

    /**
     * @notice Signals that authorization decrease was requested for the staking provider
     * @param stakingProvider Staking provider address
     * @param fromAmount Current amount of authorized tokens
     * @param toAmount Amount of authorization to decrease
     */
    event AuthorizationDecreaseRequested(
        address indexed stakingProvider,
        uint96 fromAmount,
        uint96 toAmount
    );

    /**
     * @notice Signals that authorization decrease was approved for the staking provider
     * @param stakingProvider Staking provider address
     * @param fromAmount Previous amount of authorized tokens
     * @param toAmount Decreased amount of authorized tokens
     */
    event AuthorizationDecreaseApproved(
        address indexed stakingProvider,
        uint96 fromAmount,
        uint96 toAmount
    );

    /**
     * @notice Signals that authorization was resynchronized with Threshold staking contract
     * @param stakingProvider Staking provider address
     * @param fromAmount Previous amount of authorized tokens
     * @param toAmount Resynchronized amount of authorized tokens
     */
    event AuthorizationReSynchronized(
        address indexed stakingProvider,
        uint96 fromAmount,
        uint96 toAmount
    );

    /**
     * @notice Signals that the staking provider was slashed
     * @param stakingProvider Staking provider address
     * @param penalty Slashing penalty
     * @param investigator Investigator address
     * @param reward Value of reward provided to investigator (in units of T)
     */
    event Slashed(
        address indexed stakingProvider,
        uint256 penalty,
        address indexed investigator,
        uint256 reward
    );

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
     * @notice Signals that a staking provider made a commitment
     * @param stakingProvider Staking provider address
     * @param endCommitment End of commitment
     */
    event CommitmentMade(address indexed stakingProvider, uint256 endCommitment);

    /**
     * @notice Signals that manual child synchronization was called
     * @param stakingProvider Staking provider address
     * @param authorized Amount of authorized tokens to synchronize
     * @param operator Operator address to synchronize
     */
    event ManualChildSynchronizationSent(
        address indexed stakingProvider,
        uint96 authorized,
        address operator
    );

    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint64 operatorStartTimestamp;
        uint96 authorized;
        uint96 deauthorizing; // TODO real usage only in getActiveStakingProviders, maybe remove?
        uint64 endDeauthorization;
        uint96 tReward;
        uint160 rewardPerTokenPaid;
        uint64 endCommitment;
    }

    uint256 public constant REWARD_PER_TOKEN_MULTIPLIER = 10 ** 3;
    uint256 internal constant FLOATING_POINT_DIVISOR = REWARD_PER_TOKEN_MULTIPLIER * 10 ** 18;

    uint96 public immutable minimumAuthorization;
    uint256 public immutable minOperatorSeconds;
    uint256 public immutable rewardDuration;
    uint256 public immutable deauthorizationDuration;

    uint64 public immutable commitmentDurationOption1;
    uint64 public immutable commitmentDurationOption2;
    uint64 public immutable commitmentDurationOption3;
    uint64 public immutable commitmentDurationOption4;
    uint64 public immutable commitmentDeadline;

    IStaking public immutable tStaking;
    IERC20 public immutable token;

    ITACoRootToChild public childApplication;
    address public adjudicator;

    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromOperator;

    address public rewardDistributor;
    uint256 public periodFinish;
    uint256 public rewardRateDecimals;
    uint256 public lastUpdateTime;
    uint160 public rewardPerTokenStored;
    uint96 public authorizedOverall;

    /**
     * @notice Constructor sets address of token contract and parameters for staking
     * @param _token T token contract
     * @param _tStaking T token staking contract
     * @param _minimumAuthorization Amount of minimum allowable authorization
     * @param _minOperatorSeconds Min amount of seconds while an operator can't be changed
     * @param _rewardDuration Duration of one reward cycle in seconds
     * @param _deauthorizationDuration Duration of decreasing authorization in seconds
     * @param _commitmentDurationOptions Options for commitment duration
     * @param _commitmentDeadline Last date to make a commitment
     */
    constructor(
        IERC20 _token,
        IStaking _tStaking,
        uint96 _minimumAuthorization,
        uint256 _minOperatorSeconds,
        uint256 _rewardDuration,
        uint256 _deauthorizationDuration,
        uint64[] memory _commitmentDurationOptions,
        uint64 _commitmentDeadline
    ) {
        uint256 totalSupply = _token.totalSupply();
        require(
            _rewardDuration != 0 &&
                _tStaking.authorizedStake(address(this), address(this)) == 0 &&
                totalSupply > 0 &&
                _commitmentDurationOptions.length >= 1 &&
                _commitmentDurationOptions.length <= 4,
            "Wrong input parameters"
        );
        // This require is only to check potential overflow for 10% reward
        require(
            (totalSupply / 10) * FLOATING_POINT_DIVISOR <= type(uint160).max &&
                _minimumAuthorization >= 10 ** 18 &&
                _rewardDuration >= 1 days,
            "Potential overflow"
        );
        rewardDuration = _rewardDuration;
        deauthorizationDuration = _deauthorizationDuration;
        minimumAuthorization = _minimumAuthorization;
        token = _token;
        tStaking = _tStaking;
        minOperatorSeconds = _minOperatorSeconds;
        commitmentDurationOption1 = _commitmentDurationOptions[0];
        commitmentDurationOption2 = _commitmentDurationOptions.length >= 2
            ? _commitmentDurationOptions[1]
            : 0;
        commitmentDurationOption3 = _commitmentDurationOptions.length >= 3
            ? _commitmentDurationOptions[2]
            : 0;
        commitmentDurationOption4 = _commitmentDurationOptions.length >= 4
            ? _commitmentDurationOptions[3]
            : 0;
        commitmentDeadline = _commitmentDeadline;
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
    modifier onlyStakingContract() {
        require(msg.sender == address(tStaking), "Caller must be the T staking contract");
        _;
    }

    /**
     * @dev Checks caller is a staking provider or stake owner
     */
    modifier onlyOwnerOrStakingProvider(address _stakingProvider) {
        require(isAuthorized(_stakingProvider), "Not owner or provider");
        if (_stakingProvider != msg.sender) {
            (address owner, , ) = tStaking.rolesOf(_stakingProvider);
            require(owner == msg.sender, "Not owner or provider");
        }
        _;
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize() external initializer {
        __Ownable_init(msg.sender);
    }

    /**
     * @notice Set contract for multi-chain interactions
     */
    function setChildApplication(ITACoRootToChild _childApplication) external onlyOwner {
        require(address(_childApplication).code.length > 0, "Child app must be contract");
        childApplication = _childApplication;
    }

    /**
     * @notice Set adjudicator contract. If zero then slashing is disabled
     */
    function setAdjudicator(address _adjudicator) external onlyOwner {
        require(
            address(_adjudicator) != address(adjudicator),
            "New address must not be equal to the current one"
        );
        adjudicator = _adjudicator;
    }

    /**
     *  @notice Returns authorization-related parameters of the application.
     *  @dev The minimum authorization is also returned by `minimumAuthorization()`
     *       function, as a requirement of `IApplication` interface.
     *  @return _minimumAuthorization The minimum authorization amount required
     *          so that operator can participate in the application.
     *  @return authorizationDecreaseDelay Delay in seconds that needs to pass
     *          between the time authorization decrease is requested and the
     *          time that request gets approved. Protects against free-riders
     *          earning rewards and not being active in the network.
     *  @return authorizationDecreaseChangePeriod Authorization decrease change
     *         period in seconds. It is the time, before authorization decrease
     *         delay end, during which the pending authorization decrease
     *         request can be overwritten.
     *         If set to 0, pending authorization decrease request can not be
     *         overwritten until the entire `authorizationDecreaseDelay` ends.
     *         If set to value equal `authorizationDecreaseDelay`, request can
     *         always be overwritten.
     */
    function authorizationParameters()
        external
        view
        override
        returns (
            uint96 _minimumAuthorization,
            uint64 authorizationDecreaseDelay,
            uint64 authorizationDecreaseChangePeriod
        )
    {
        return (
            minimumAuthorization,
            uint64(deauthorizationDuration),
            uint64(deauthorizationDuration)
        );
    }

    //------------------------Reward------------------------------

    /**
     * @notice Set reward distributor address
     */
    function setRewardDistributor(address _rewardDistributor) external onlyOwner {
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
            info.tReward = availableRewards(_stakingProvider);
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
     * @notice Returns current value of reward per token * multiplier
     */
    function rewardPerToken() public view returns (uint160) {
        if (authorizedOverall == 0) {
            return rewardPerTokenStored;
        }
        uint256 result = rewardPerTokenStored +
            ((lastTimeRewardApplicable() - lastUpdateTime) * rewardRateDecimals) /
            authorizedOverall;
        return result.toUint160();
    }

    /**
     * @notice Returns amount of reward in T units for the staking provider
     * @param _stakingProvider Staking provider address
     */
    function availableRewards(address _stakingProvider) public view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (!info.operatorConfirmed) {
            return info.tReward;
        }
        uint256 result = (uint256(info.authorized) * (rewardPerToken() - info.rewardPerTokenPaid)) /
            FLOATING_POINT_DIVISOR +
            info.tReward;
        return result.toUint96();
    }

    /**
     * @notice Transfer reward for the next period. Can be called only by distributor
     * @param _reward Amount of reward
     */
    function pushReward(uint96 _reward) external updateReward(address(0)) {
        require(msg.sender == rewardDistributor, "Only distributor can push rewards");
        require(_reward > 0, "Reward must be specified");
        require(authorizedOverall > 0, "No active staking providers");
        if (block.timestamp >= periodFinish) {
            rewardRateDecimals = (uint256(_reward) * FLOATING_POINT_DIVISOR) / rewardDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRateDecimals;
            rewardRateDecimals =
                (uint256(_reward) * FLOATING_POINT_DIVISOR + leftover) /
                rewardDuration;
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
    function withdrawRewards(address _stakingProvider) external updateReward(_stakingProvider) {
        address beneficiary = getBeneficiary(_stakingProvider);
        require(msg.sender == beneficiary, "Caller must be beneficiary");

        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        uint96 value = info.tReward;
        require(value > 0, "No reward to withdraw");
        info.tReward = 0;
        emit RewardPaid(_stakingProvider, beneficiary, value);
        token.safeTransfer(beneficiary, value);
    }

    //------------------------Authorization------------------------------
    /**
     * @notice Recalculate `authorizedOverall` if desync happened
     */
    function resynchronizeAuthorizedOverall(
        StakingProviderInfo storage _info,
        uint96 _properAmount
    ) internal {
        if (_info.authorized != _properAmount) {
            authorizedOverall -= _info.authorized - _properAmount;
        }
    }

    /**
     * @notice Recalculate reward and save increased authorization. Can be called only by staking contract
     * @param _stakingProvider Address of staking provider
     * @param _fromAmount Amount of previously authorized tokens to TACo application by staking provider
     * @param _toAmount Amount of authorized tokens to TACo application by staking provider
     */
    function authorizationIncreased(
        address _stakingProvider,
        uint96 _fromAmount,
        uint96 _toAmount
    ) external override onlyStakingContract updateReward(_stakingProvider) {
        require(
            _stakingProvider != address(0) && _toAmount > 0,
            "Input parameters must be specified"
        );
        require(_toAmount >= minimumAuthorization, "Authorization must be greater than minimum");

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
        _updateAuthorization(_stakingProvider, info);
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
    ) external override onlyStakingContract updateReward(_stakingProvider) {
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
            _releaseOperator(_stakingProvider);
        }
        _updateAuthorization(_stakingProvider, info);
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
    ) external override onlyStakingContract updateReward(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(_toAmount <= info.authorized, "Amount to decrease greater than authorized");
        require(
            _toAmount == 0 || _toAmount >= minimumAuthorization,
            "Resulting authorization will be less than minimum"
        );
        require(
            info.endCommitment <= block.timestamp,
            "Can't request deauthorization before end of commitment"
        );
        if (info.operatorConfirmed) {
            resynchronizeAuthorizedOverall(info, _fromAmount);
        }

        info.authorized = _fromAmount;
        info.deauthorizing = _fromAmount - _toAmount;
        info.endDeauthorization = uint64(block.timestamp + deauthorizationDuration);
        emit AuthorizationDecreaseRequested(_stakingProvider, _fromAmount, _toAmount);
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * @notice Approve request of decreasing authorization. Can be called by anyone
     * @param _stakingProvider Address of staking provider
     */
    function approveAuthorizationDecrease(
        address _stakingProvider
    ) external updateReward(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.deauthorizing > 0, "There is no deauthorizing in process");
        require(
            info.endDeauthorization <= block.timestamp,
            "Authorization decrease has not finished yet"
        );

        uint96 toAmount = tStaking.approveAuthorizationDecrease(_stakingProvider);

        if (info.operatorConfirmed) {
            authorizedOverall -= info.authorized - toAmount;
        }

        emit AuthorizationDecreaseApproved(_stakingProvider, info.authorized, toAmount);
        info.authorized = toAmount;
        info.deauthorizing = 0;
        info.endDeauthorization = 0;

        if (info.authorized == 0) {
            _releaseOperator(_stakingProvider);
        }
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * @notice Read authorization from staking contract and store it. Can be called by anyone
     * @param _stakingProvider Address of staking provider
     */
    function resynchronizeAuthorization(
        address _stakingProvider
    ) external updateReward(_stakingProvider) {
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
            _releaseOperator(_stakingProvider);
        }
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * @notice Make a commitment to not request authorization decrease for specified duration
     * @param _stakingProvider Staking provider address
     * @param _commitmentDuration Duration of commitment
     */
    function makeCommitment(
        address _stakingProvider,
        uint64 _commitmentDuration
    ) external onlyOwnerOrStakingProvider(_stakingProvider) {
        require(block.timestamp < commitmentDeadline, "Commitment window closed");
        require(
            _commitmentDuration > 0 &&
                (_commitmentDuration == commitmentDurationOption1 ||
                    _commitmentDuration == commitmentDurationOption2 ||
                    _commitmentDuration == commitmentDurationOption3 ||
                    _commitmentDuration == commitmentDurationOption4),
            "Commitment duration must be equal to one of options"
        );
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.endDeauthorization == 0, "Commitment can't be made during deauthorization");
        require(info.endCommitment == 0, "Commitment already made");
        info.endCommitment = uint64(block.timestamp) + _commitmentDuration;
        emit CommitmentMade(_stakingProvider, info.endCommitment);
    }

    //-------------------------Main-------------------------
    /**
     * @notice Returns staking provider for specified operator
     */
    function operatorToStakingProvider(address _operator) external view returns (address) {
        return _stakingProviderFromOperator[_operator];
    }

    /**
     * @notice Returns operator for specified staking provider
     */
    function stakingProviderToOperator(address _stakingProvider) external view returns (address) {
        return stakingProviderInfo[_stakingProvider].operator;
    }

    /**
     * @notice Get all tokens delegated to the staking provider
     */
    function authorizedStake(address _stakingProvider) external view returns (uint96) {
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    /**
     * @notice Get all tokens delegated to the staking provider
     */
    function getEligibleAmount(StakingProviderInfo storage _info) internal view returns (uint96) {
        return _info.authorized - _info.deauthorizing;
    }

    /**
     * @notice Returns the amount of stake that is pending authorization
     *         decrease for the given staking provider. If no authorization
     *         decrease has been requested, returns zero.
     */
    function pendingAuthorizationDecrease(
        address _stakingProvider
    ) external view override returns (uint96) {
        return stakingProviderInfo[_stakingProvider].deauthorizing;
    }

    /**
     * @notice Returns the remaining time in seconds that needs to pass before
     *         the requested authorization decrease can be approved.
     */
    function remainingAuthorizationDecreaseDelay(
        address _stakingProvider
    ) external view override returns (uint64) {
        uint256 endDeauthorization = stakingProviderInfo[_stakingProvider].endDeauthorization;
        if (endDeauthorization <= block.timestamp) {
            return 0;
        }
        return uint64(endDeauthorization - block.timestamp);
    }

    /**
     * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
     * @param _startIndex Start index for looking in providers array
     * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
     * @return allAuthorizedTokens Sum of authorized tokens for active providers
     * @return activeStakingProviders Array of providers and their authorized tokens.
     * Providers addresses stored together with amounts as bytes32
     * @dev Note that activeStakingProviders is an array of bytes32, but you want addresses and amounts.
     * Careful when used directly!
     */
    function getActiveStakingProviders(
        uint256 _startIndex,
        uint256 _maxStakingProviders
    ) external view returns (uint256 allAuthorizedTokens, bytes32[] memory activeStakingProviders) {
        uint256 endIndex = stakingProviders.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxStakingProviders != 0 && _startIndex + _maxStakingProviders < endIndex) {
            endIndex = _startIndex + _maxStakingProviders;
        }
        activeStakingProviders = new bytes32[](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address stakingProvider = stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            uint256 eligibleAmount = getEligibleAmount(info);
            if (eligibleAmount < minimumAuthorization || !info.operatorConfirmed) {
                continue;
            }
            // bytes20 -> bytes32 adds padding after address: <address><12 zeros>
            // uint96 -> uint256 adds padding before uint96: <20 zeros><amount>
            activeStakingProviders[resultIndex++] =
                bytes32(bytes20(stakingProvider)) |
                bytes32(uint256(eligibleAmount));
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeStakingProviders, resultIndex)
        }
    }

    /**
     * @notice Returns beneficiary related to the staking provider
     */
    function getBeneficiary(
        address _stakingProvider
    ) public view returns (address payable beneficiary) {
        (, beneficiary, ) = tStaking.rolesOf(_stakingProvider);
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
     *  @notice Used by staking provider to set operator address that will
     *          operate a node. The operator address must be unique.
     *          Reverts if the operator is already set for the staking provider
     *          or if the operator address is already in use.
     */
    function registerOperator(address _operator) external override {
        bondOperator(msg.sender, _operator);
    }

    /**
     * @notice Bond operator
     * @param _stakingProvider Staking provider address
     * @param _operator Operator address. Must be an EOA, not a contract address
     */
    function bondOperator(
        address _stakingProvider,
        address _operator
    ) public onlyOwnerOrStakingProvider(_stakingProvider) updateReward(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        address previousOperator = info.operator;
        require(
            _operator != previousOperator,
            "Specified operator is already bonded with this provider"
        );
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
            require(
                _stakingProviderFromOperator[_operator] == address(0),
                "Specified operator is already in use"
            );
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
        emit OperatorBonded(_stakingProvider, _operator, previousOperator, block.timestamp);

        info.operatorConfirmed = false;
        childApplication.updateOperator(_stakingProvider, _operator);
    }

    /**
     * @notice Make a confirmation by operator
     */
    function confirmOperatorAddress(address _operator) external override {
        require(
            msg.sender == address(childApplication),
            "Only child application allowed to confirm operator"
        );
        address stakingProvider = _stakingProviderFromOperator[_operator];
        // TODO only in case of desync, maybe just exit?
        // require(stakingProvider != address(0), "Operator has no bond with staking provider");
        if (stakingProvider == address(0)) {
            return;
        }

        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        if (!info.operatorConfirmed) {
            updateRewardInternal(stakingProvider);
            info.operatorConfirmed = true;
            authorizedOverall += info.authorized;
            emit OperatorConfirmed(stakingProvider, _operator);
        }
    }

    //-------------------------XChain-------------------------

    /**
     * @notice Resets operator confirmation
     */
    function _releaseOperator(address _stakingProvider) internal {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        _stakingProviderFromOperator[info.operator] = address(0);
        info.operator = address(0);
        info.operatorConfirmed = false;
        info.endDeauthorization = 0;
        info.endCommitment = 0;
        childApplication.updateOperator(_stakingProvider, address(0));
    }

    /**
     * @notice Send updated authorized amount to xchain contract
     */
    function _updateAuthorization(
        address _stakingProvider,
        StakingProviderInfo storage _info
    ) internal {
        // TODO send both authorized and eligible amounts in case of slashing from child app
        uint96 eligibleAmount = getEligibleAmount(_info);
        childApplication.updateAuthorization(_stakingProvider, eligibleAmount);
    }

    /**
     * @notice Manual signal to the bridge with the current state of the specified staking provider
     * @dev This method is useful only in case of issues with the bridge
     */
    function manualChildSynchronization(address _stakingProvider) external {
        require(_stakingProvider != address(0), "Staking provider must be specified");
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        emit ManualChildSynchronizationSent(_stakingProvider, info.authorized, info.operator);
        _updateAuthorization(_stakingProvider, info);
        childApplication.updateOperator(_stakingProvider, info.operator);
    }

    //-------------------------Slashing-------------------------
    /**
     * @notice Slash the provider's stake and reward the investigator
     * @param _stakingProvider Staking provider address
     * @param _penalty Penalty
     * @param _investigator Investigator
     */
    function slash(address _stakingProvider, uint96 _penalty, address _investigator) external {
        require(msg.sender == adjudicator, "Only adjudicator allowed to slash");
        address[] memory stakingProviderWrapper = new address[](1);
        stakingProviderWrapper[0] = _stakingProvider;
        tStaking.seize(_penalty, 100, _investigator, stakingProviderWrapper);
    }
}
