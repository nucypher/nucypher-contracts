// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./ITACoRootToChild.sol";
import "../../threshold/ITACoChildApplication.sol";
import "./ITACoChildToRoot.sol";

/**
 * @title TACoChildApplication
 * @notice TACoChildApplication
 */
contract TACoChildApplication is AccessControl, ITACoRootToChild, ITACoChildApplication {
    bytes32 public constant UPDATE_ROLE = keccak256("UPDATE_ROLE");
    bytes32 public constant DEPLOYER_ROLE = keccak256("DEPLOYER_ROLE");

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

    constructor(ITACoChildToRoot _rootApplication, address[] memory updaters) {
        require(
            address(_rootApplication) != address(0),
            "Address for root application must be specified"
        );
        rootApplication = _rootApplication;

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        for (uint256 i = 0; i < updaters.length; i++) {
            _grantRole(UPDATE_ROLE, updaters[i]);
        }
    }

    function setCoordinator(address _coordinator) external onlyRole(DEPLOYER_ROLE) {
        require(coordinator == address(0), "Coordinator already set");
        require(_coordinator != address(0), "Coordinator must be specified");
        // require(_coordinator.numberOfRituals() >= 0, "Invalid coordinator");
        coordinator = _coordinator;

        // TODO reset role?
    }

    function authorizedStake(address _stakingProvider) external view returns (uint96) {
        return stakingProviderInfo[_stakingProvider].authorized;
    }

    function updateOperator(
        address stakingProvider,
        address operator
    ) external override onlyRole(UPDATE_ROLE) {
        _updateOperator(stakingProvider, operator);
    }

    function updateAuthorization(
        address stakingProvider,
        uint96 amount
    ) external override onlyRole(UPDATE_ROLE) {
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

    function batchUpdate(bytes32[] calldata updateInfo) external override onlyRole(UPDATE_ROLE) {
        require(updateInfo.length % 2 == 0, "bad length");
        for (uint256 i = 0; i < updateInfo.length; i += 2) {
            bytes32 word0 = updateInfo[i];
            bytes32 word1 = updateInfo[i + 1];

            address provider = address(bytes20(word0));
            uint96 amount = uint96(uint256(word0));
            address operator = address(bytes20(word1));

            _updateOperator(provider, operator);
            _updateAuthorization(provider, amount);
        }
    }

    function confirmOperatorAddress(address _operator) external override {
        require(msg.sender == coordinator, "Only Coordinator allowed to confirm operator");
        address stakingProvider = stakingProviderFromOperator[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        if (info.operatorConfirmed) {
            return;
        }
        require(info.authorized > 0, "No stake associated with the operator");
        info.operatorConfirmed = true;
        rootApplication.confirmOperatorAddress(_operator);
    }
}
