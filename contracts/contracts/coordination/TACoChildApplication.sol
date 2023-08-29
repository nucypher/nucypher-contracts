// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/AccessControlUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "./ITACoRootToChild.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./ITACoChildToRoot.sol";

/**
 * @title TACoChildApplication
 * @notice TACoChildApplication
 */
contract TACoChildApplication is ITACoRootToChild, ITACoChildApplication, Initializable {
    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint96 authorized;
        // TODO: what about undelegations etc?
    }

    ITACoChildToRoot public immutable rootApplication;
    address public coordinator;

    mapping(address => StakingProviderInfo) public stakingProviderInfo;
    mapping(address => address) public stakingProviderFromOperator;

    /**
     * @dev Checks caller is root application
     */
    modifier onlyRootApplication() {
        require(msg.sender == address(rootApplication), "Caller must be the root application");
        _;
    }

    constructor(ITACoChildToRoot _rootApplication) {
        require(
            address(_rootApplication) != address(0),
            "Address for root application must be specified"
        );
        rootApplication = _rootApplication;
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(address _coordinator) external initializer {
        require(coordinator == address(0), "Coordinator already set");
        require(_coordinator != address(0), "Coordinator must be specified");
        // require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;
    }

    function authorizedStake(address _stakingProvider) external view returns (uint96) {
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    function updateOperator(
        address stakingProvider,
        address operator
    ) external override onlyRootApplication {
        _updateOperator(stakingProvider, operator);
    }

    function updateAuthorization(
        address stakingProvider,
        uint96 amount
    ) external override onlyRootApplication {
        _updateAuthorization(stakingProvider, amount);
    }

    function _updateOperator(address stakingProvider, address operator) internal {
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        address oldOperator = info.operator;

        if (operator != oldOperator) {
            info.operator = operator;
            // Update operator to provider mapping
            stakingProviderFromOperator[oldOperator] = address(0);
            stakingProviderFromOperator[operator] = stakingProvider;
            info.operatorConfirmed = false;
            // TODO placeholder to notify Coordinator

            emit OperatorUpdated(stakingProvider, operator);
        }
    }

    function _updateAuthorization(address stakingProvider, uint96 amount) internal {
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        uint96 fromAmount = info.authorized;

        if (amount != fromAmount) {
            info.authorized = amount;
            emit AuthorizationUpdated(stakingProvider, amount);
        }
    }

    function confirmOperatorAddress(address _operator) external override {
        require(msg.sender == coordinator, "Only Coordinator allowed to confirm operator");
        address stakingProvider = stakingProviderFromOperator[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        require(info.authorized > 0, "No stake associated with the operator");
        // TODO maybe allow second confirmation, just do not send root call?
        require(!info.operatorConfirmed, "Can't confirm same operator twice");
        info.operatorConfirmed = true;
        rootApplication.confirmOperatorAddress(_operator);
    }
}

contract TestnetTACoChildApplication is AccessControlUpgradeable, TACoChildApplication {
    bytes32 public constant UPDATE_ROLE = keccak256("UPDATE_ROLE");

    constructor(ITACoChildToRoot _rootApplication) TACoChildApplication(_rootApplication) {}

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
        uint96 amount
    ) external onlyRole(UPDATE_ROLE) {
        _updateAuthorization(stakingProvider, amount);
    }
}
