// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/AccessControlUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./ITACoRootToChild.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./ITACoChildToRoot.sol";
import "./Coordinator.sol";

/**
 * @title TACoChildApplication
 * @notice TACoChildApplication
 */
contract TACoChildApplication is ITACoRootToChild, ITACoChildApplication, Initializable {
    /**
     * @notice Signals that the staking provider was penalized
     * @param stakingProvider Staking provider address
     */
    event Penalized(address indexed stakingProvider);

    /**
     * @notice Signals that the staking provider was released
     * @param stakingProvider Staking provider address
     */
    event Released(address indexed stakingProvider);

    /**
     * @notice Signals that the release tx was resent
     * @param stakingProvider Staking provider address
     */
    event ReleaseResent(address indexed stakingProvider);

    struct StakingProviderInfo {
        address operator;
        uint96 authorized;
        bool operatorConfirmed;
        uint248 index; // index in stakingProviders array + 1
        uint96 deauthorizing;
        uint64 endDeauthorization;
        uint256 stub;
        bool released;
    }

    ITACoChildToRoot public immutable rootApplication;
    address public coordinator;

    uint96 public immutable minimumAuthorization;

    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) public operatorToStakingProvider;
    address public adjudicator;
    uint32[] public activeRituals;

    /**
     * @dev Checks caller is root application
     */
    modifier onlyRootApplication() {
        require(msg.sender == address(rootApplication), "Caller must be the root application");
        _;
    }

    constructor(ITACoChildToRoot _rootApplication, uint96 _minimumAuthorization) {
        require(
            address(_rootApplication) != address(0),
            "Address for root application must be specified"
        );
        require(_minimumAuthorization > 0, "Minimum authorization must be specified");
        rootApplication = _rootApplication;
        minimumAuthorization = _minimumAuthorization;
        _disableInitializers();
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(address _coordinator, address _adjudicator) external initializer {
        require(coordinator == address(0) || adjudicator == address(0), "Contracts already set");
        require(
            _coordinator != address(0) && _adjudicator != address(0),
            "Contracts must be specified"
        );
        require(
            address(Coordinator(_coordinator).application()) == address(this),
            "Invalid coordinator"
        );
        coordinator = _coordinator;
        adjudicator = _adjudicator;
    }

    function setActiveRituals(uint32[] memory _activeRituals) external reinitializer(2) {
        activeRituals = _activeRituals;
    }

    function authorizedStake(address _stakingProvider) external view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (info.released) {
            return 0;
        }
        return info.authorized;
    }

    /**
     * @notice Returns the amount of stake that is pending authorization
     *         decrease for the given staking provider. If no authorization
     *         decrease has been requested, returns zero.
     */
    function pendingAuthorizationDecrease(address _stakingProvider) external view returns (uint96) {
        return stakingProviderInfo[_stakingProvider].deauthorizing;
    }

    /**
     * @notice Returns the amount of stake that are going to be effectively
     *         staked until the specified date. I.e: in case a deauthorization
     *         is going to be made during this period, the returned amount will
     *         be the staked amount minus the deauthorizing amount.
     */
    function eligibleStake(
        address _stakingProvider,
        uint256 _endDate
    ) public view returns (uint96) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (info.released) {
            return 0;
        }

        uint96 eligibleAmount = info.authorized;
        if (0 < info.endDeauthorization && info.endDeauthorization < _endDate) {
            eligibleAmount -= info.deauthorizing;
        }

        return eligibleAmount;
    }

    function updateOperator(
        address stakingProvider,
        address operator
    ) external override onlyRootApplication {
        _updateOperator(stakingProvider, operator);
    }

    // TODO only for backward compatibility
    function updateAuthorization(
        address stakingProvider,
        uint96 authorized
    ) external override onlyRootApplication {
        _updateAuthorization(stakingProvider, authorized, 0, 0);
    }

    function updateAuthorization(
        address stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization
    ) external override onlyRootApplication {
        _updateAuthorization(stakingProvider, authorized, deauthorizing, endDeauthorization);
    }

    function _updateOperator(address stakingProvider, address operator) internal {
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        address oldOperator = info.operator;

        if (stakingProvider == address(0) || operator == oldOperator) {
            return;
        }

        if (info.index == 0) {
            stakingProviders.push(stakingProvider);
            info.index = uint248(stakingProviders.length);
        }

        info.operator = operator;
        // Update operator to provider mapping
        operatorToStakingProvider[oldOperator] = address(0);
        if (operator != address(0)) {
            operatorToStakingProvider[operator] = stakingProvider;
        }
        info.operatorConfirmed = false;
        // TODO placeholder to notify Coordinator

        emit OperatorUpdated(stakingProvider, operator);
    }

    function _updateAuthorization(
        address stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization
    ) internal {
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];

        if (
            stakingProvider == address(0) ||
            (authorized == info.authorized &&
                deauthorizing == info.deauthorizing &&
                endDeauthorization == info.endDeauthorization)
        ) {
            return;
        }

        // increasing authorization considered as intention to stay with the network
        if (authorized > info.authorized) {
            info.released = false;
        }

        info.authorized = authorized;
        info.deauthorizing = deauthorizing;
        info.endDeauthorization = endDeauthorization;
        emit AuthorizationUpdated(stakingProvider, authorized, deauthorizing, endDeauthorization);
    }

    function confirmOperatorAddress(address _operator) external override {
        require(msg.sender == coordinator, "Only Coordinator allowed to confirm operator");
        address stakingProvider = operatorToStakingProvider[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        require(
            info.authorized >= minimumAuthorization,
            "Authorization must be greater than minimum"
        );
        // TODO maybe allow second confirmation, just do not send root call?
        require(!info.operatorConfirmed, "Can't confirm same operator twice");
        info.operatorConfirmed = true;
        emit OperatorConfirmed(stakingProvider, _operator);
        rootApplication.confirmOperatorAddress(_operator);
    }

    /**
     * @notice Penalize the staking provider's future reward
     * @param _stakingProvider Staking provider address
     */
    function penalize(address _stakingProvider) external override {
        require(msg.sender == address(adjudicator), "Only adjudicator allowed to penalize");
        rootApplication.penalize(_stakingProvider);
        emit Penalized(_stakingProvider);
    }

    /**
     * @notice Return the length of the array of staking providers
     */
    function getStakingProvidersLength() external view returns (uint256) {
        return stakingProviders.length;
    }

    /**
     * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
     * @param _startIndex Start index for looking in providers array
     * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
     * @param _cohortDuration Duration during which staking provider should be active. 0 means forever
     * @return allAuthorizedTokens Sum of authorized tokens for active providers
     * @return activeStakingProviders Array of providers and their authorized tokens.
     * Providers addresses stored together with amounts as bytes32
     * @dev Note that activeStakingProviders is an array of bytes32, but you want addresses and amounts
     * Careful when used directly!
     */
    function getActiveStakingProviders(
        uint256 _startIndex,
        uint256 _maxStakingProviders,
        uint32 _cohortDuration
    ) public view returns (uint96 allAuthorizedTokens, bytes32[] memory activeStakingProviders) {
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
            uint96 eligibleAmount = eligibleStake(stakingProvider, endDate);
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

    // TODO only for backward compatibility
    function getActiveStakingProviders(
        uint256 _startIndex,
        uint256 _maxStakingProviders
    ) external view returns (uint96 allAuthorizedTokens, bytes32[] memory activeStakingProviders) {
        return getActiveStakingProviders(_startIndex, _maxStakingProviders, 0);
    }

    function release(
        address _stakingProvider
    ) external override(ITACoRootToChild, ITACoChildToRoot) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(
            msg.sender == _stakingProvider ||
                msg.sender == info.operator ||
                msg.sender == address(rootApplication) ||
                msg.sender == coordinator,
            "Can't call release"
        );
        if (info.released) {
            return;
        }
        // check all active rituals
        for (uint256 i = 0; i < activeRituals.length; i++) {
            uint32 ritualId = activeRituals[i];
            if (
                Coordinator(coordinator).isRitualActive(ritualId) &&
                Coordinator(coordinator).isParticipant(ritualId, _stakingProvider)
            ) {
                // still part of the ritual
                return;
            }
        }
        info.released = true;
        emit Released(_stakingProvider);
        rootApplication.release(_stakingProvider);
    }

    function resendRelease(address _stakingProvider) external {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        if (info.released) {
            emit ReleaseResent(_stakingProvider);
            rootApplication.release(_stakingProvider);
        }
    }
}

contract TestnetTACoChildApplication is AccessControlUpgradeable, TACoChildApplication {
    bytes32 public constant UPDATE_ROLE = keccak256("UPDATE_ROLE");

    constructor(
        ITACoChildToRoot _rootApplication,
        uint96 _minimumAuthorization
    ) TACoChildApplication(_rootApplication, _minimumAuthorization) {}

    function initialize(address _coordinator, address[] memory updaters) external initializer {
        coordinator = _coordinator;
        for (uint256 i = 0; i < updaters.length; i++) {
            _grantRole(UPDATE_ROLE, updaters[i]);
        }
    }

    function forceUpdateOperator(
        address stakingProvider,
        address operator
    ) external onlyRole(UPDATE_ROLE) {
        _updateOperator(stakingProvider, operator);
    }

    function forceUpdateAuthorization(
        address stakingProvider,
        uint96 authorized,
        uint96 deauthorizing,
        uint64 endDeauthorization
    ) external onlyRole(UPDATE_ROLE) {
        _updateAuthorization(stakingProvider, authorized, deauthorizing, endDeauthorization);
    }
}
