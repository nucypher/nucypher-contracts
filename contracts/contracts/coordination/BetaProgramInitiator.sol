// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import "./Coordinator.sol";

contract BetaProgramInitiator {
    using SafeERC20 for IERC20;

    event RequestRegistered(
        address indexed sender,
        uint256 indexed requestIndex,
        address[] providers,
        address authority,
        uint32 duration,
        IEncryptionAuthorizer accessController,
        uint256 payment
    );

    event RequestCanceled(address indexed sender, uint256 indexed requestIndex);

    event RequestExecuted(uint256 indexed requestIndex, uint256 indexed ritualId);

    event FailedRequestRefunded(uint256 indexed requestIndex, uint256 refundAmount);

    struct InitiationRequest {
        address[] providers;
        address authority;
        uint32 duration;
        IEncryptionAuthorizer accessController;
        address sender;
        uint32 ritualId;
        uint256 payment;
    }

    uint32 public constant NO_RITUAL = type(uint32).max;

    Coordinator public immutable coordinator;
    IERC20 public immutable currency;
    address public immutable executor; // TODO transferable role?

    InitiationRequest[] public requests;

    constructor(Coordinator _coordinator, address _executor) {
        require(_executor != address(0), "Invalid parameters");
        coordinator = _coordinator;
        currency = coordinator.currency();
        executor = _executor;
    }

    function getRequestsLength() external view returns (uint256) {
        return requests.length;
    }

    function getProviders(uint256 requestIndex) external view returns (address[] memory) {
        InitiationRequest storage request = requests[requestIndex];
        return request.providers;
    }

    function registerInitiationRequest(
        address[] calldata providers,
        address authority,
        uint32 duration,
        IEncryptionAuthorizer accessController
    ) external returns (uint256 requestIndex) {
        uint256 ritualCost = coordinator.getRitualInitiationCost(providers, duration);

        requestIndex = requests.length;
        InitiationRequest storage request = requests.push();
        request.providers = providers;
        request.authority = authority;
        request.duration = duration;
        request.accessController = accessController;
        request.sender = msg.sender;
        request.ritualId = NO_RITUAL;
        request.payment = ritualCost;

        emit RequestRegistered(
            msg.sender,
            requestIndex,
            providers,
            authority,
            duration,
            accessController,
            ritualCost
        );
        currency.safeTransferFrom(msg.sender, address(this), ritualCost);

        return requestIndex;
    }

    function cancelInitiationRequest(uint256 requestIndex) external {
        require(requestIndex < requests.length, "Non-existent request");
        InitiationRequest storage request = requests[requestIndex];
        address sender = request.sender;
        require(msg.sender == sender || msg.sender == executor, "Not allowed to cancel");

        uint256 ritualCost = request.payment;
        require(request.ritualId == NO_RITUAL, "Request already executed");
        require(ritualCost != 0, "Request canceled");

        // Erase payment and transfer refund to original sender
        request.payment = 0;
        emit RequestCanceled(msg.sender, requestIndex);
        currency.safeTransfer(sender, ritualCost);
        // TODO consider gas refund by setting zero values
    }

    function executeInitiationRequest(uint256 requestIndex) external {
        require(msg.sender == executor, "Only executor can call");

        require(requestIndex < requests.length, "Non-existent request");
        InitiationRequest storage request = requests[requestIndex];
        require(request.ritualId == NO_RITUAL, "Request already executed");
        require(request.payment != 0, "Request canceled");

        address[] memory providers = request.providers;
        uint32 duration = request.duration;
        uint256 ritualCost = coordinator.getRitualInitiationCost(providers, duration);
        require(ritualCost == request.payment, "Ritual initiation cost has changed");
        currency.approve(address(coordinator), ritualCost);

        uint32 ritualId = coordinator.initiateRitual(
            providers,
            request.authority,
            duration,
            request.accessController
        );
        request.ritualId = ritualId;
        emit RequestExecuted(requestIndex, ritualId);
    }

    function refundFailedRequest(uint256 requestIndex) external {
        require(requestIndex < requests.length, "Non-existent request");
        InitiationRequest storage request = requests[requestIndex];
        uint32 ritualId = request.ritualId;
        require(request.ritualId != NO_RITUAL, "Request is not executed");
        require(request.payment != 0, "Refund already processed");

        Coordinator.RitualState state = coordinator.getRitualState(ritualId);
        require(
            state == Coordinator.RitualState.DKG_INVALID ||
                state == Coordinator.RitualState.DKG_TIMEOUT,
            "Ritual is not failed"
        );

        // Process pending fees in Coordinator, if necessary
        uint256 refundAmount = coordinator.feeDeduction(request.payment, request.duration);
        if (coordinator.pendingFees(ritualId) > 0) {
            coordinator.processPendingFee(ritualId);
        }

        // Erase payment and transfer refund to original sender
        request.payment = 0;
        currency.safeTransfer(request.sender, refundAmount);
        emit FailedRequestRefunded(requestIndex, refundAmount);
        // TODO consider gas refund by setting zero values
    }
}
