// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./ManagedAllowList.sol";

contract SubscriptionManager is ManagedAllowList {
    struct Subscription {
        address subscriber;
        uint256 amount;
        uint256 period; // Represents the end timestamp of the subscription
    }

    mapping(bytes32 => Subscription) public subscriptions;

    event SubscriptionCreated(
        uint32 indexed ritualId,
        address indexed subscriber,
        uint256 amount,
        uint256 period
    );
    event SubscriptionTerminated(uint32 indexed ritualId, address indexed subscriber);
    event SubscriptionRenewed(
        uint32 indexed ritualId,
        address indexed subscriber,
        uint256 amount,
        uint256 period
    );

    function createSubscription(
        uint32 ritualId,
        address _subscriber,
        uint256 _amount,
        uint256 _period
    ) external onlyCohortAuthority(ritualId) {
        bytes32 key = lookupKey(ritualId, _subscriber);
        require(
            subscriptions[key].subscriber == address(0),
            "Subscriber already has an active subscription"
        );

        Subscription memory newSubscription = Subscription({
            subscriber: _subscriber,
            amount: _amount,
            period: _period
        });

        subscriptions[key] = newSubscription;

        emit SubscriptionCreated(ritualId, _subscriber, _amount, _period);
    }

    function terminateSubscription(
        uint32 ritualId,
        address _subscriber
    ) external onlySubscriber(ritualId, _subscriber) {
        bytes32 key = lookupKey(ritualId, _subscriber);
        require(
            subscriptions[key].subscriber != address(0),
            "No active subscription found for the subscriber"
        );

        delete subscriptions[key];

        emit SubscriptionTerminated(ritualId, _subscriber);

        // TODO: Return the _amount to the subscriber. Is it a native asset or ERC20?
    }

    // TODO: Handle a native asset or ERC20 as _amount
    function renewSubscription(
        uint32 ritualId,
        address _subscriber,
        uint256 _amount,
        uint256 _period
    ) external onlyCohortAuthority(ritualId) {
        bytes32 key = lookupKey(ritualId, _subscriber);
        require(
            subscriptions[key].subscriber != address(0),
            "No active subscription found for the subscriber"
        );

        Subscription storage subscription = subscriptions[key];
        subscription.amount = _amount;
        subscription.period = _period;

        emit SubscriptionRenewed(ritualId, _subscriber, _amount, _period);
    }

    function _beforeIsAuthorized(
        uint32 ritualId,
        bytes memory evidence,
        bytes memory ciphertextHeader
    ) internal view override {
        bytes32 digest = keccak256(ciphertextHeader);
        address recoveredAddress = digest.toEthSignedMessageHash().recover(evidence);
        Subscription memory subscription = subscriptions[lookupKey(ritualId, recoveredAddress)];
        require(
            subscription.subscriber != address(0) && subscription.period >= block.timestamp,
            "Subscriber is not authorized or subscription has expired"
        );
    }

    // TODO: What do I do with the `bool value`?
    function _beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata addresses,
        bool value
    ) internal override {
        for (uint256 i = 0; i < addresses.length; i++) {
            Subscription memory subscription = subscriptions[lookupKey(ritualId, addresses[i])];
            require(
                subscription.subscriber != address(0) && subscription.period >= block.timestamp,
                "Subscriber is not authorized or subscription has expired"
            );
        }
    }
}
