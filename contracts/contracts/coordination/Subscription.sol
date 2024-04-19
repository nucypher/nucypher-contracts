// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
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

    Coordinator public coordinator;
    IERC20 public feeToken;

    // Mapping from subscription ID to subscription info
    mapping(uint32 => SubscriptionInfo) public subscriptions;

    // Mapping from (ritualId, address) to subscription ID
    mapping(bytes32 => uint32) public subscribers;

    uint32 public numberOfSubscriptions;

    // TODO: DAO Treasury
    address public beneficiary;

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
     * @notice Returns the key used to lookup authorizations
     * @param ritualId The ID of the ritual
     * @param encryptor The address of the encryptor
     * @return The key used to lookup authorizations
     */
    function lookupKey(uint32 ritualId, address encryptor) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(ritualId, encryptor));
    }

    /**
     * @notice Creates a new subscription
     * @param ritualId The ID of the ritual
     * @return The ID of the new subscription
     */
    function newSubscription(uint32 ritualId) external returns (uint256) {
        uint32 subscriptionId = numberOfSubscriptions;
        SubscriptionInfo storage sub = subscriptions[subscriptionId];
        sub.subscriber = msg.sender;
        paySubscriptionFor(subscriptionId);

        subscribers[lookupKey(ritualId, msg.sender)] = subscriptionId;

        numberOfSubscriptions += 1;

        // TODO: Emit event?

        return subscriptionId;
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

        // TODO: Emit event?
    }

    /**
     * @notice Checks if a spender can spend from a subscription
     * @param subscriptionId The ID of the subscription
     * @param spender The address of the spender
     * @return True if the spender can spend from the subscription, false otherwise
     */
    function canSpendFromSubscription(
        uint32 subscriptionId, // TODO: Currently unused
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

    // TODO: Withdraw methods for DAO Treasury, cancel subscription, etc

    /**
     * @notice Withdraws the contract balance to the beneficiary
     * @param amount The amount to withdraw
     */
    function withdrawToBeneficiary(uint256 amount) external {
        require(msg.sender == beneficiary, "Only the beneficiary can withdraw");
        uint256 contractBalance = feeToken.balanceOf(address(this));
        require(contractBalance >= amount, "Insufficient contract balance");
        feeToken.safeTransfer(beneficiary, amount);
    }

    /**
     * @notice Cancels a subscription
     * @param ritualId The ID of the ritual
     * @param subscriptionId The ID of the subscription
     */
    function cancelSubscription(uint32 ritualId, uint32 subscriptionId) external {
        require(
            msg.sender == subscriptions[subscriptionId].subscriber,
            "Only the subscriber can cancel the subscription"
        );
        uint256 refundAmount = subscriptions[subscriptionId].paidFor;
        feeToken.safeTransfer(msg.sender, refundAmount);
        delete subscriptions[subscriptionId];
        delete subscribers[lookupKey(ritualId, msg.sender)];

        // TODO: Emit event?
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
        return authorizationActionCaps[subscribers[lookupKey(ritualId, spender)]];
    }
}
