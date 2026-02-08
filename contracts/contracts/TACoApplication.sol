// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/utils/math/SafeCast.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
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
     * @notice Signals that manual child synchronization was called
     * @param stakingProvider Staking provider address
     * @param authorized Amount of authorized tokens to synchronize
     * @param operator Operator address to synchronize
     */
    event ManualChildSynchronizationSent(
        address indexed stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization,
        address operator
    );

    /**
     * @notice Signals that the staking provider was released
     * @param stakingProvider Staking provider address
     */
    event Released(address indexed stakingProvider);

    /**
     * @notice Signals that the staking provider migrated stake to TACo
     * @param stakingProvider Staking provider address
     * @param authorized Amount of authorized tokens to synchronize
     */
    event Migrated(address indexed stakingProvider, uint96 authorized);

    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint64 operatorStartTimestamp;
        uint96 authorized;
        uint96 deauthorizing;
        // uint64 _endDeauthorization;
        // uint96 _tReward;
        // uint160 _rewardPerTokenPaid;
        // uint64 _legacyEndCommitment;
        // uint256 _stub;
        // uint192 _penaltyPercent;
        // uint64 _endPenalty;
        // TODO check gap size and offset for deauthorizing
        uint256[10] _gap;
        address owner;
        address beneficiary;
    }

    uint96 public immutable minimumAuthorization;
    uint256 public immutable minOperatorSeconds;

    IStaking public immutable tStaking;
    IERC20 public immutable token;

    ITACoRootToChild public childApplication;
    address private _adjudicator;

    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromOperator;

    // address private _rewardDistributor;
    // uint256 private _periodFinish;
    // uint256 private _rewardRateDecimals;
    // uint256 private _lastUpdateTime;
    // uint160 private _rewardPerTokenStored;
    // uint96 private _authorizedOverall;

    // address private _rewardContract;
    uint256[6] private _gap;

    mapping(address => bool) public stakingProviderReleased;
    mapping(address => bool) public allowList;

    /**
     * @notice Constructor sets address of token contract and parameters for staking
     * @param _token T token contract
     * @param _tStaking T token staking contract
     * @param _minimumAuthorization Amount of minimum allowable authorization
     * @param _minOperatorSeconds Min amount of seconds while an operator can't be changed
     */
    constructor(
        IERC20 _token,
        IStaking _tStaking,
        uint96 _minimumAuthorization,
        uint256 _minOperatorSeconds
    ) {
        uint256 totalSupply = _token.totalSupply();
        require(
            _tStaking.authorizedStake(address(this), address(this)) == 0 && totalSupply > 0,
            "Wrong input parameters"
        );
        minimumAuthorization = _minimumAuthorization;
        token = _token;
        tStaking = _tStaking;
        minOperatorSeconds = _minOperatorSeconds;
        _disableInitializers();
    }

    /**
     * @dev Checks caller is T staking contract or contract Owner
     */
    modifier onlyStakingContract() {
        require(
            msg.sender == address(tStaking) || msg.sender == owner(),
            "Caller must be the T staking contract or contract owner"
        );
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
        return (minimumAuthorization, 0, 0);
    }

    //------------------------Authorization------------------------------

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
    ) external override onlyStakingContract {
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

        info.authorized = _toAmount;
        emit AuthorizationIncreased(_stakingProvider, _fromAmount, _toAmount);
        _updateAuthorization(_stakingProvider, info);

        stakingProviderReleased[_stakingProvider] = false;
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
    ) external override onlyStakingContract {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];

        uint96 decrease = info.authorized - _toAmount;
        if (info.deauthorizing > decrease) {
            info.deauthorizing -= decrease;
        } else {
            info.deauthorizing = 0;
        }

        info.authorized = _toAmount;

        // if (info.authorized < info.deauthorizing) {
        //     info.deauthorizing = info.authorized;
        // }
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
    ) external override onlyStakingContract {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(_toAmount <= info.authorized, "Amount to decrease greater than authorized");
        require(
            _toAmount == 0 || _toAmount >= minimumAuthorization,
            "Resulting authorization will be less than minimum"
        );

        info.authorized = _fromAmount;
        info.deauthorizing = _fromAmount - _toAmount;
        emit AuthorizationDecreaseRequested(_stakingProvider, _fromAmount, _toAmount);
        _updateAuthorization(_stakingProvider, info);
        if (_toAmount < minimumAuthorization) {
            childApplication.release(_stakingProvider);
        }
    }

    /**
     * @notice Approve request of decreasing authorization. Can be called by anyone
     * @param _stakingProvider Address of staking provider
     */
    function approveAuthorizationDecrease(address _stakingProvider) external {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.deauthorizing > 0, "There is no deauthorizing in process");

        uint96 toAmount = tStaking.approveAuthorizationDecrease(_stakingProvider);
        require(
            stakingProviderReleased[_stakingProvider] || toAmount >= minimumAuthorization,
            "Node has not finished leaving process"
        );

        emit AuthorizationDecreaseApproved(_stakingProvider, info.authorized, toAmount);
        info.authorized = toAmount;
        info.deauthorizing = 0;

        if (info.authorized == 0) {
            _releaseOperator(_stakingProvider);
        }
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * @notice Read authorization from staking contract and store it. Can be called by anyone
     * @param _stakingProvider Address of staking provider
     */
    function resynchronizeAuthorization(address _stakingProvider) external {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        uint96 newAuthorized = tStaking.authorizedStake(_stakingProvider, address(this));
        require(info.authorized > newAuthorized, "Nothing to synchronize");
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
        if (stakingProviderReleased[_stakingProvider]) {
            return 0;
        }
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    /**
     * @notice Returns the amount of stake that are going to be effectively
     *         staked until the specified date. I.e: in case a deauthorization
     *         is going to be made during this period, the returned amount will
     *         be the staked amount minus the deauthorizing amount.
     */
    function eligibleStake(address _stakingProvider, uint256) public view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (stakingProviderReleased[_stakingProvider]) {
            return 0;
        }

        uint96 eligibleAmount = info.authorized;
        // if (0 < info.endDeauthorization && info.endDeauthorization < _endDate) {
        eligibleAmount -= info.deauthorizing;
        // }

        return eligibleAmount;
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
    function remainingAuthorizationDecreaseDelay(address) external view override returns (uint64) {
        return 0;
    }

    /**
     * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
     * @param _startIndex Start index for looking in providers array
     * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
     * @param _cohortDuration Duration during which staking provider should be active. 0 means forever
     * @return allAuthorizedTokens Sum of authorized tokens for active providers
     * @return activeStakingProviders Array of providers and their authorized tokens.
     * Providers addresses stored together with amounts as bytes32
     * @dev Note that activeStakingProviders is an array of bytes32, but you want addresses and amounts.
     * Careful when used directly!
     */
    function getActiveStakingProviders(
        uint256 _startIndex,
        uint256 _maxStakingProviders,
        uint32 _cohortDuration
    ) external view returns (uint256 allAuthorizedTokens, bytes32[] memory activeStakingProviders) {
        uint256 endIndex = stakingProviders.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxStakingProviders != 0 && _startIndex + _maxStakingProviders < endIndex) {
            endIndex = _startIndex + _maxStakingProviders;
        }
        activeStakingProviders = new bytes32[](endIndex - _startIndex);
        allAuthorizedTokens = 0;
        uint256 endDate = _cohortDuration == 0
            ? type(uint256).max
            : block.timestamp + _cohortDuration;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address stakingProvider = stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            uint256 eligibleAmount = eligibleStake(stakingProvider, endDate);
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
    ) public onlyOwnerOrStakingProvider(_stakingProvider) {
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
            info.operatorConfirmed = true;
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
        childApplication.updateOperator(_stakingProvider, address(0));
    }

    /**
     * @notice Send updated authorized amount to xchain contract
     */
    function _updateAuthorization(
        address _stakingProvider,
        StakingProviderInfo storage _info
    ) internal {
        childApplication.updateAuthorization(
            _stakingProvider,
            _info.authorized,
            _info.deauthorizing,
            0
        );
    }

    /**
     * @notice Manual signal to the bridge with the current state of the specified staking provider
     * @dev This method is useful only in case of issues with the bridge
     */
    function manualChildSynchronization(address _stakingProvider) external {
        require(_stakingProvider != address(0), "Staking provider must be specified");
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        emit ManualChildSynchronizationSent(
            _stakingProvider,
            info.authorized,
            info.deauthorizing,
            0,
            info.operator
        );
        _updateAuthorization(_stakingProvider, info);
        childApplication.updateOperator(_stakingProvider, info.operator);
    }

    function release(address _stakingProvider) external override(ITACoChildToRoot) {
        require(
            msg.sender == address(childApplication),
            "Only child application allowed to release"
        );

        if (_stakingProvider == address(0)) {
            return;
        }

        stakingProviderReleased[_stakingProvider] = true;
        emit Released(_stakingProvider);
    }

    function penalize(address) external override {
        revert("Deprecated");
    }

    function withdrawRewards(address) external override {
        revert("Deprecated");
    }

    function availableRewards(address) external view override returns (uint96) {
        return 0;
    }

    //------------------------Migration------------------------------

    function controlAllowList(address[] memory _stakingProviders, bool enable) external onlyOwner {
        for (uint256 i = 0; i < _stakingProviders.length; i++) {
            allowList[_stakingProviders[i]] = enable;
        }
    }

    function migrateFromThreshold(
        address _stakingProvider
    ) external onlyOwnerOrStakingProvider(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.owner == address(0), "Migration completed");
        require(allowList[_stakingProvider], "Migration is not allowed");
        _migrateFromThreshold(_stakingProvider, info);
    }

    function batchMigrateFromThreshold(address[] memory _stakingProviders) external onlyOwner {
        require(_stakingProviders.length > 0, "Array is empty");
        for (uint256 i = 0; i < _stakingProviders.length; i++) {
            address stakingProvider = _stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            if (info.owner != address(0)) {
                continue;
            }
            _migrateFromThreshold(stakingProvider, info);
        }
    }

    function _migrateFromThreshold(
        address _stakingProvider,
        StakingProviderInfo storage _info
    ) internal {
        require(eligibleStake(_stakingProvider, 0) > 0, "Not an active staker");
        (address owner, address beneficiary, ) = tStaking.rolesOf(_stakingProvider);
        _info.owner = owner;
        _info.beneficiary = beneficiary;
        uint96 tokensToTransfer = Math.min(minimumAuthorization, _info.authorized).toUint96();
        tStaking.migrateAndRelease(_stakingProvider, tokensToTransfer);
        _info.authorized = tokensToTransfer;
        emit Migrated(_stakingProvider, tokensToTransfer);
    }

    function rolesOf(
        address _stakingProvider
    ) external view returns (address owner, address beneficiary) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        owner = info.owner;
        beneficiary = info.beneficiary;
    }
}
