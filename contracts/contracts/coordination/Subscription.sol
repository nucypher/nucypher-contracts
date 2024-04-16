// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./Coordinator.sol";

abstract contract Subscription {

    struct SubscriptionInfo {
        uint256 paidFor;
        uint256 spent;
        uint256 expiration;
        address subscriber;
    }

    Coordinator coordinator;
    IERC20 feeToken;

    mapping(uint32 => SubscriptionInfo) public subscriptions;
    uint32 public numberOfSubscriptions;

    constructor(Coordinator _coordinator, IERC20 _feeToken){
        // TODO: coordintaor and token checks
        coordinator = _coordinator;
        feeToken = _feeToken;
    }

    function subscriptionFee() pure public returns(uint256) {
        return 42 * 10**20;  // TODO
    }

    function baseExpiration() pure public returns(uint256) {
        return 52 weeks;  // TODO
    }

    function newSubscription() external returns(uint256){

        uint32 subscriptionId = numberOfSubscriptions;
        SubscriptionInfo storage sub = subscriptions[subscriptionId];
        sub.subscriber = msg.sender;
        paySubscriptionFor(subscriptionId);

        numberOfSubscriptions += 1;
    }

    function paySubscriptionFor(uint32 subscriptionId) public virtual {
        uint256 amount = subscriptionFee();

        SubscriptionInfo storage sub = subscriptions[subscriptionId];
        sub.paidFor += amount;
        sub.expiration += baseExpiration();

        feeToken.safeTransferFrom(msg.sender, address(this), amount);
    }

    function canSpendFromSubscription(
        uint32 subscriptionId,
        address spender
    ) public returns(bool){
        // By default, only coordinator can spend from subscription
        return spender == address(coordinator);
    }

    function spendFromSubscription(uint32 subscriptionId, uint256 amount) external {
        require(canSpendFromSubscription(subscriptionId, msg.sender));
        feeToken.safeTransferFrom(address(this), msg.sender, amount);
    }

    // TODO: Withdraw methods for DAO Treasury, cancel subscription, etc
}

// An upfront subscription for a cohort with a predefined duration and a max number of encryptors
contract UpfrontSubscriptionWithEncryptorsCap is Subscription {

    uint256 constant DEFAULT_CAP = 1000;

    mapping(uint32 => uint256) authorizationActionCaps;

    constructor(Coordinator _coordinator, IERC20 _feeToken)
        Subscription(_coordinator, _feeToken){

    }

    function paySubscriptionFor(uint32 subscriptionId) public virtual override {
        super.paySubscriptionFor(subscriptionId);
        authorizationActionCaps[subscriptionId] += DEFAULT_CAP;
    }
}
