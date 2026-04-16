// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/utils/math/SafeCast.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./coordination/ITACoRootToChild.sol";
import "./coordination/ITACoChildToRoot.sol";
import "./coordination/PenaltyBoard.sol";

/**
 * @title TACo Application
 * @notice Contract distributes rewards for participating in app and slashes for violating rules
 */
contract TACoApplication is ITACoChildToRoot, OwnableUpgradeable {
    using SafeERC20 for IERC20;
    using SafeCast for uint256;

    /**
     * @notice Signals that unstake was requested for the staking provider
     * @param stakingProvider Staking provider address
     */
    event UnstakeRequested(address indexed stakingProvider);

    /**
     * @notice Signals that unstake was approved for the staking provider
     * @param stakingProvider Staking provider address
     */
    event UnstakeApproved(address indexed stakingProvider);

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
     * @notice Signals that new stake was initialized
     * @param stakingProvider Staking provider address
     * @param owner Owner address
     * @param beneficiary Beneficiary address
     * @param amount Amount of authorized tokens
     */
    event Staked(
        address indexed stakingProvider,
        address indexed owner,
        address indexed beneficiary,
        uint96 amount
    );

    /**
     * @notice Signals that the staking provider was released
     * @param stakingProvider Staking provider address
     */
    event Released(address indexed stakingProvider);

    /**
     * @notice Signals that the staking provider was added without stake
     * @param stakingProvider Staking provider address
     */
    event StakelessProviderAdded(address indexed stakingProvider);

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
        bool stakeless;
    }

    uint96 public immutable minimumAuthorization;
    uint256 public immutable minOperatorSeconds;

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
    uint256[8] private _gap;

    // mapping(address => bool) public stakingProviderReleased;
    // mapping(address => bool) public allowList;
    PenaltyBoard public penaltyBoard;

    /**
     * @notice Constructor sets address of token contract and parameters for staking
     * @param _token T token contract
     * @param _minimumAuthorization Amount of minimum allowable authorization
     * @param _minOperatorSeconds Min amount of seconds while an operator can't be changed
     */
    constructor(IERC20 _token, uint96 _minimumAuthorization, uint256 _minOperatorSeconds) {
        uint256 totalSupply = _token.totalSupply();
        require(totalSupply > 0, "Wrong input parameters");
        minimumAuthorization = _minimumAuthorization;
        token = _token;
        minOperatorSeconds = _minOperatorSeconds;
        _disableInitializers();
    }

    /**
     * @dev Checks caller is a staking provider or stake owner
     */
    modifier onlyOwnerOrStakingProvider(address _stakingProvider) {
        require(isAuthorized(_stakingProvider), "Not owner or provider");
        if (_stakingProvider != msg.sender) {
            address owner = stakingProviderInfo[_stakingProvider].owner;
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
     * @notice Set contract for compensation
     */
    function setPenaltyBoard(PenaltyBoard _penaltyBoard) external onlyOwner {
        require(address(_penaltyBoard).code.length > 0, "PenaltyBoard must be contract");
        penaltyBoard = _penaltyBoard;
    }

    //------------------------Staking------------------------------

    function initializeStake(
        address _stakingProvider,
        address _owner,
        address _beneficiary
    ) external onlyOwner {
        require(
            _stakingProvider != address(0) && _owner != address(0) && _beneficiary != address(0),
            "Parameters are empty"
        );
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.authorized == 0 && info.owner == address(0), "Stake already initialized");
        require(
            _stakingProviderFromOperator[_stakingProvider] == address(0),
            "Staker is an operator"
        );

        info.owner = _owner;
        info.beneficiary = _beneficiary;
        info.authorized = minimumAuthorization;
        emit Staked(_stakingProvider, _owner, _beneficiary, info.authorized);
        token.safeTransferFrom(_owner, address(this), info.authorized);
        _updateAuthorization(_stakingProvider, info);
    }

    /**
     * @notice Register request of unstaking
     * @param _stakingProvider Address of staking provider
     */
    function requestUnstake(
        address _stakingProvider
    ) external onlyOwnerOrStakingProvider(_stakingProvider) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.deauthorizing == 0, "Unstake already requested");

        info.deauthorizing = info.authorized;
        emit UnstakeRequested(_stakingProvider);
        _updateAuthorization(_stakingProvider, info);
        childApplication.release(_stakingProvider);
    }

    function release(address _stakingProvider) external override(ITACoChildToRoot) {
        require(
            msg.sender == address(childApplication),
            "Only child application allowed to release"
        );

        if (_stakingProvider == address(0)) {
            return;
        }
        approveUnstake(_stakingProvider);
    }

    /**
     * @notice Approve request of unstaking
     * @param _stakingProvider Address of staking provider
     */
    function approveUnstake(address _stakingProvider) internal {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.deauthorizing > 0, "There is no unstaking in process");

        emit UnstakeApproved(_stakingProvider);
        uint96 authorized = info.authorized;
        info.authorized = 0;
        info.deauthorizing = 0;

        _releaseOperator(_stakingProvider);
        _updateAuthorization(_stakingProvider, info);
        if (!info.stakeless) {
            token.safeTransfer(info.owner, authorized);
        }
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
     * @notice Returns the amount of stake that are going to be effectively
     *         staked until the specified date. I.e: in case a deauthorization
     *         is going to be made during this period, the returned amount will
     *         be the staked amount minus the deauthorizing amount.
     */
    function eligibleStake(address _stakingProvider) public view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];

        uint96 eligibleAmount = info.authorized;
        if (eligibleAmount > info.deauthorizing) {
            eligibleAmount -= info.deauthorizing;
        } else {
            eligibleAmount = 0;
        }

        return eligibleAmount;
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
            uint256 eligibleAmount = eligibleStake(stakingProvider);
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
    function getBeneficiary(address _stakingProvider) public view returns (address beneficiary) {
        beneficiary = stakingProviderInfo[_stakingProvider].beneficiary;
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
    function registerOperator(address _operator) external {
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

        penaltyBoard.computeRewards(_stakingProvider);
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
            penaltyBoard.enableRewards(stakingProvider);
            info.operatorConfirmed = true;
            emit OperatorConfirmed(stakingProvider, _operator);
        }
    }

    //-------------------------XChain-------------------------

    /**
     * @notice Resets operator confirmation
     */
    function _releaseOperator(address _stakingProvider) internal {
        penaltyBoard.computeRewards(_stakingProvider);
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

    function penalize(address) external override {
        revert("Deprecated");
    }

    function rolesOf(
        address _stakingProvider
    ) external view returns (address owner, address beneficiary) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        owner = info.owner;
        beneficiary = info.beneficiary;
    }

    function addStakelessProvider(address _stakingProvider, address _owner) external onlyOwner {
        require(
            _stakingProvider != address(0) && _owner != address(0),
            "Parameters must be specified"
        );
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(info.owner == address(0), "Staker already exists");
        require(
            _stakingProviderFromOperator[_stakingProvider] == address(0) ||
                _stakingProviderFromOperator[_stakingProvider] == _stakingProvider,
            "A provider can't be an operator for another provider"
        );

        info.authorized = minimumAuthorization;
        info.owner = _owner;
        info.stakeless = true;
        emit StakelessProviderAdded(_stakingProvider);
        _updateAuthorization(_stakingProvider, info);
    }

    function isEligibleForReward(address _stakingProvider) external view returns (bool) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        return !info.stakeless && info.operatorConfirmed;
    }
}
