// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./SigningCoordinator.sol";

contract SigningCohortInitiator is Ownable {
    using SafeERC20 for IERC20;

    event RequestExecuted(
        uint32 indexed cohortId,
        address indexed initiator,
        address authority,
        uint256 chainId
    );

    event FailedRequestRefunded(uint32 indexed cohortId, uint256 refundAmount);

    event ExtensionExecuted(uint32 indexed cohortId, uint32 additionalDuration);

    struct InitiationRequest {
        address initiator;
        address authority;
        uint256 chainId;
    }

    uint32 public constant NO_RITUAL = type(uint32).max;

    SigningCoordinator public immutable signingCoordinator;
    IERC20 public immutable currency;
    uint256 public immutable feeRatePerSecond;
    address[] public defaultProviders;
    uint16 public defaultThreshold;
    uint32 public defaultDuration;

    mapping(uint32 => InitiationRequest) public requests;
    uint256 public totalPendingFees;
    mapping(uint256 => uint256) public pendingFees;

    constructor(
        SigningCoordinator _signingCoordinator,
        IERC20 _currency,
        uint256 _feeRatePerSecond,
        address[] memory _defaultProviders,
        uint16 _defaultThreshold,
        uint32 _defaultDuration
    ) Ownable(msg.sender) {
        require(address(_signingCoordinator) != address(0), "Invalid signing coordinator");
        require(address(_currency) != address(0), "Invalid currency");
        require(_feeRatePerSecond > 0, "Invalid fee rate");
        require(_defaultProviders.length > 0, "Invalid default providers");
        require(
            _defaultThreshold > 0 && _defaultThreshold <= _defaultProviders.length,
            "Invalid default threshold"
        );
        require(_defaultDuration > 0, "Invalid default duration");

        signingCoordinator = _signingCoordinator;
        currency = _currency;
        feeRatePerSecond = _feeRatePerSecond;
        defaultProviders = _defaultProviders;
        defaultThreshold = _defaultThreshold;
        defaultDuration = _defaultDuration;
    }

    function getCohortCost(
        uint256 numberOfProviders,
        uint32 duration
    ) public view returns (uint256) {
        require(numberOfProviders > 0, "Invalid cohort size");
        require(duration > 0, "Invalid cohort duration");
        return feeRatePerSecond * numberOfProviders * duration;
    }

    function feeDeduction(uint256, uint256) public pure returns (uint256) {
        return 0;
    }

    function processPayment(
        address initiator,
        uint32 cohortId,
        uint256 numberOfProviders,
        uint32 duration
    ) internal {
        uint256 cohortCost = getCohortCost(numberOfProviders, duration);
        require(cohortCost > 0, "Invalid cohort cost");
        totalPendingFees += cohortCost;
        pendingFees[cohortId] += cohortCost;
        currency.safeTransferFrom(initiator, address(this), cohortCost);
    }

    function processPendingFee(uint32 cohortId) internal returns (uint256 refundableFee) {
        SigningCoordinator.SigningCohortState state = signingCoordinator.getSigningCohortState(
            cohortId
        );
        require(
            state == SigningCoordinator.SigningCohortState.TIMEOUT ||
                state == SigningCoordinator.SigningCohortState.ACTIVE ||
                state == SigningCoordinator.SigningCohortState.EXPIRED,
            "Ritual is not ended"
        );
        uint256 pending = pendingFees[cohortId];
        require(pending > 0, "No pending fees for this ritual");

        // Finalize fees for this ritual
        totalPendingFees -= pending;
        delete pendingFees[cohortId];
        // Transfer fees back to initiator if failed
        if (state == SigningCoordinator.SigningCohortState.TIMEOUT) {
            // Refund everything minus cost of renting cohort for a day
            address initiator = requests[cohortId].initiator;
            (uint32 initTimestamp, uint32 endTimestamp) = signingCoordinator.getTimestamps(
                cohortId
            );
            uint256 duration = endTimestamp - initTimestamp;
            refundableFee = pending - feeDeduction(pending, duration);
            currency.safeTransfer(initiator, refundableFee);
        }
        return refundableFee;
    }

    function withdrawTokens(uint256 amount) external onlyOwner {
        require(
            amount <= currency.balanceOf(address(this)) - totalPendingFees,
            "Can't withdraw pending fees"
        );
        currency.safeTransfer(msg.sender, amount);
    }

    function establishSigningCohort(
        address authority,
        uint256 chainId
    ) external returns (uint32 cohortId) {
        uint32 expectedCohortId = uint32(signingCoordinator.numberOfSigningCohorts());
        processPayment(msg.sender, expectedCohortId, defaultProviders.length, defaultDuration);
        uint32 cohortId = signingCoordinator.initiateSigningCohort(
            chainId,
            authority,
            defaultProviders,
            defaultThreshold,
            defaultDuration
        );
        // TODO: a bit awkward
        require(cohortId == expectedCohortId, "Cohort ID mismatch");

        InitiationRequest storage request = requests[cohortId];
        request.initiator = msg.sender;
        request.authority = authority;
        request.chainId = chainId;

        emit RequestExecuted(cohortId, msg.sender, authority, chainId);
        return cohortId;
    }

    function deployAdditionalChain(uint32 cohortId, uint256 chainId) external {
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        InitiationRequest storage request = requests[cohortId];
        require(
            msg.sender == request.initiator || msg.sender == request.authority,
            "Only initiator or authority can deploy additional chain"
        );
        require(request.chainId != chainId, "Chain ID already exists for this cohort");

        // TODO: do we want additional payment here?
        signingCoordinator.deployAdditionalChainForSigningMultisig(chainId, cohortId);
    }

    function refundFailedRequest(uint32 cohortId) external {
        SigningCoordinator.SigningCohortState state = signingCoordinator.getSigningCohortState(
            cohortId
        );
        require(state == SigningCoordinator.SigningCohortState.TIMEOUT, "Request did not fail");

        InitiationRequest storage request = requests[cohortId];
        require(msg.sender == request.initiator, "Only initiator can request refund");

        // process pending fees before refunding to get the correct refund amount
        uint256 refundableFee = processPendingFee(cohortId);
        emit FailedRequestRefunded(cohortId, refundableFee);
        // TODO consider gas refund by setting zero values
    }

    function extendSigningCohort(uint32 cohortId) external {
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        InitiationRequest storage request = requests[cohortId];
        require(msg.sender == request.initiator, "Only initiator can extend cohort duration");
        processPayment(msg.sender, cohortId, defaultProviders.length, defaultDuration);

        signingCoordinator.extendSigningCohortDuration(cohortId, defaultDuration);
        emit ExtensionExecuted(cohortId, defaultDuration);
    }
}
