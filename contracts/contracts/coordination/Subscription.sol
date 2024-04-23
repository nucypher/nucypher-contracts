// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../lib/LookupKey.sol";
import "./Coordinator.sol";

using SafeERC20 for IERC20;

/**
 * @title Subscription
 * @notice Manages the subscription information for rituals.
 * @dev This contract is abstract and should be extended by a concrete implementation.
 * It maintains a reference to a Coordinator contract and a fee token (ERC20).
 * Each subscription has an associated SubscriptionInfo struct which keeps track of the subscription details.
 */
abstract contract Subscription {
    struct SubscriptionInfo {
        uint256 paidFor;
        uint256 spent;
        uint256 expiration;
        address subscriber;
    }

    Coordinator public immutable coordinator;
    IERC20 public immutable feeToken;

    // Mapping from subscription ID to subscription info
    mapping(uint32 => SubscriptionInfo) public subscriptions;

    // Mapping from (ritualId, address) to subscription ID
    mapping(bytes32 => uint32) public subscribers;

    uint32 public numberOfSubscriptions;

    // TODO: DAO Treasury
    // TODO: Should it be updatable?
    address public immutable beneficiary;

    /**
     * @notice Emitted when a subscription is created
     * @param subscriptionId The ID of the subscription
     * @param subscriber The address of the subscriber
     * @param ritualId The ID of the ritual
     */
    event SubscriptionCreated(
        uint32 indexed subscriptionId,
        address indexed subscriber,
        uint32 indexed ritualId
    );

    /**
     * @notice Emitted when a subscription is cancelled
     * @param subscriptionId The ID of the subscription
     * @param subscriber The address of the subscriber
     * @param ritualId The ID of the ritual
     */
    event SubscriptionCancelled(
        uint32 indexed subscriptionId,
        address indexed subscriber,
        uint32 indexed ritualId
    );

    /**
     * @notice Emitted when a subscription is paid
     * @param subscriptionId The ID of the subscription
     * @param subscriber The address of the subscriber
     * @param amount The amount paid
     */
    event SubscriptionPaid(
        uint32 indexed subscriptionId,
        address indexed subscriber,
        uint256 amount
    );

    /**
     * @notice Emitted when a subscription is spent
     * @param beneficiary The address of the beneficiary
     * @param amount The amount withdrawn
     * @param amount The amount spent
     */
    event WithdrawalToBeneficiary(address indexed beneficiary, uint256 amount);

    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _feeToken The address of the fee token contract
     * @param _beneficiary The address of the beneficiary
     */
    constructor(Coordinator _coordinator, IERC20 _feeToken, address _beneficiary) {
        require(address(_coordinator) != address(0), "Coordinator cannot be the zero address");
        require(address(_feeToken) != address(0), "Fee token cannot be the zero address");
        require(_beneficiary != address(0), "Beneficiary cannot be the zero address");
        coordinator = _coordinator;
        feeToken = _feeToken;
        beneficiary = _beneficiary;
    }

    /**
     * @notice Returns the subscription fee
     * @return The subscription fee
     */
    function subscriptionFee() public pure returns (uint256) {
        return 42 * 10 ** 20; // TODO
    }

    /**
     * @notice Returns the base expiration duration
     * @return The base expiration duration
     */
    function baseExpiration() public pure returns (uint256) {
        return 52 weeks; // TODO
    }

    /**
     * @notice Creates a new subscription
     * @param ritualId The ID of the ritual
     */
    function newSubscription(uint32 ritualId) external {
        uint32 subscriptionId = numberOfSubscriptions;
        SubscriptionInfo storage sub = subscriptions[subscriptionId];
        sub.subscriber = msg.sender;
        paySubscriptionFor(subscriptionId);

        subscribers[LookupKey.lookupKey(ritualId, msg.sender)] = subscriptionId;
        numberOfSubscriptions += 1;

        emit SubscriptionCreated(subscriptionId, msg.sender, ritualId);
    }

    /**
     * @notice Pays for a subscription
     * @param subscriptionId The ID of the subscription
     */
    function paySubscriptionFor(uint32 subscriptionId) public virtual {
        uint256 amount = subscriptionFee();

        SubscriptionInfo storage sub = subscriptions[subscriptionId];
        sub.paidFor += amount;
        sub.expiration += baseExpiration();

        feeToken.safeTransferFrom(msg.sender, address(this), amount);

        // TODO: We already emit SubscriptionCreated, do we need this?
        emit SubscriptionPaid(subscriptionId, msg.sender, amount);
    }

    /**
     * @notice Checks if a spender can spend from a subscription
     * @param subscriptionId The ID of the subscription
     * @param spender The address of the spender
     * @return True if the spender can spend from the subscription, false otherwise
     */
    function canSpendFromSubscription(
        // TODO: Currently unused, remove?
        // solhint-disable-next-line no-unused-vars
        uint32 subscriptionId,
        address spender
    ) public returns (bool) {
        // By default, only coordinator can spend from subscription
        return spender == address(coordinator);
    }

    /**
     * @notice Spends from a subscription
     * @param subscriptionId The ID of the subscription
     * @param amount The amount to spend
     */
    function spendFromSubscription(uint32 subscriptionId, uint256 amount) external {
        require(canSpendFromSubscription(subscriptionId, msg.sender), "Unauthorized spender");
        feeToken.safeTransferFrom(address(this), msg.sender, amount);
    }

    /**
     * @notice Withdraws the contract balance to the beneficiary
     * @param amount The amount to withdraw
     */
    function withdrawToBeneficiary(uint256 amount) external {
        require(msg.sender == beneficiary, "Only the beneficiary can withdraw");

        uint256 availableAmount = 0;
        for (uint32 i = 0; i < numberOfSubscriptions; i++) {
            SubscriptionInfo storage sub = subscriptions[i];
            if (block.timestamp >= sub.expiration) {
                availableAmount += sub.paidFor - sub.spent;
            }
        }
        require(amount <= availableAmount, "Insufficient available amount");

        feeToken.safeTransfer(beneficiary, amount);

        emit WithdrawalToBeneficiary(beneficiary, amount);
    }

    /**
     * @notice Cancels a subscription
     * @param ritualId The ID of the ritual
     * @param subscriptionId The ID of the subscription
     */
    function cancelSubscription(uint32 ritualId, uint32 subscriptionId) public virtual {
        require(
            msg.sender == subscriptions[subscriptionId].subscriber,
            "Only the subscriber can cancel the subscription"
        );
        uint256 refundAmount = subscriptions[subscriptionId].paidFor;
        feeToken.safeTransfer(msg.sender, refundAmount);
        delete subscriptions[subscriptionId];
        delete subscribers[LookupKey.lookupKey(ritualId, msg.sender)];

        emit SubscriptionCancelled(subscriptionId, msg.sender, ritualId);
    }
}

/**
 * @title UpfrontSubscriptionWithEncryptorsCap
 * @notice Manages upfront subscriptions with a cap on the number of encryptors.
 * @dev This contract extends the Subscription contract and introduces a cap on the number of encryptors.
 */
contract UpfrontSubscriptionWithEncryptorsCap is Subscription {
    uint256 public constant DEFAULT_CAP = 1000;

    // Mapping from subscription ID to the number of authorization actions
    mapping(uint32 => uint256) public authorizationActionCaps;

    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _feeToken The address of the fee token contract
     */
    constructor(
        Coordinator _coordinator,
        IERC20 _feeToken,
        address _beneficiary
    ) Subscription(_coordinator, _feeToken, _beneficiary) {}

    /**
     * @notice Pays for a subscription and increases the authorization actions cap
     * @param subscriptionId The ID of the subscription
     */
    function paySubscriptionFor(uint32 subscriptionId) public virtual override {
        super.paySubscriptionFor(subscriptionId);
        authorizationActionCaps[subscriptionId] += DEFAULT_CAP;
    }

    /**
     * @notice Returns the authorization actions cap for a given ritual and spender
     * @param ritualId The ID of the ritual
     * @param spender The address of the spender
     * @return The authorization actions cap
     */
    function authorizationActionsCap(
        uint32 ritualId,
        address spender
    ) public view returns (uint256) {
        return authorizationActionCaps[subscribers[LookupKey.lookupKey(ritualId, spender)]];
    }

    /**
     * @notice Cancels a subscription and deletes the authorization actions cap
     * @param ritualId The ID of the ritual
     * @param subscriptionId The ID of the subscription
     */
    function cancelSubscription(uint32 ritualId, uint32 subscriptionId) public virtual override {
        super.cancelSubscription(ritualId, subscriptionId);
        delete authorizationActionCaps[subscriptionId];
    }
}
