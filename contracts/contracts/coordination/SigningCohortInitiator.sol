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

    event RetryFailedRequest(uint32 indexed oldCohortId, uint32 indexed newCohortId);

    event ExtensionExecuted(uint32 indexed cohortId, uint32 additionalDuration);

    struct InitiationRequest {
        address initiator;
        uint256 chainId;
    }

    SigningCoordinator public immutable signingCoordinator;
    IERC20 public immutable currency;
    uint256 public immutable feeRatePerSecond;
    address[] public defaultProviders;
    uint16 public defaultThreshold;
    uint32 public defaultDuration;

    mapping(uint32 => InitiationRequest) public requests; // cohortId -> Request

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

    function _processPayment(
        address initiator,
        uint256 numberOfProviders,
        uint32 duration
    ) internal {
        uint256 cohortCost = getCohortCost(numberOfProviders, duration);
        require(cohortCost > 0, "Invalid cohort cost");
        currency.safeTransferFrom(initiator, address(this), cohortCost);
    }

    function withdrawFees() external onlyOwner {
        uint256 fees = currency.balanceOf(address(this));
        require(fees > 0, "No fees to withdraw");
        currency.safeTransfer(msg.sender, fees);
    }

    function _createSigningCohort(address authority, uint256 chainId) internal returns (uint32) {
        uint32 cohortId = signingCoordinator.initiateSigningCohort(
            chainId,
            authority,
            defaultProviders,
            defaultThreshold,
            defaultDuration
        );

        InitiationRequest storage request = requests[cohortId];
        request.initiator = msg.sender;
        request.chainId = chainId;

        emit RequestExecuted(cohortId, msg.sender, authority, chainId);
        return cohortId;
    }

    function establishSigningCohort(address authority, uint256 chainId) external returns (uint32) {
        _processPayment(msg.sender, defaultProviders.length, defaultDuration);
        return _createSigningCohort(authority, chainId);
    }

    function deployAdditionalChain(uint32 cohortId, uint256 chainId) external {
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        InitiationRequest storage request = requests[cohortId];
        require(
            msg.sender == request.initiator ||
                msg.sender == signingCoordinator.getAuthority(cohortId),
            "Only initiator or authority can deploy additional chain"
        );
        require(request.chainId != chainId, "Chain ID already exists for this cohort");

        // TODO: do we want additional payment here?
        signingCoordinator.deployAdditionalChainForSigningMultisig(chainId, cohortId);
    }

    function retryFailedRequest(uint32 cohortId) external returns (uint32) {
        SigningCoordinator.SigningCohortState state = signingCoordinator.getSigningCohortState(
            cohortId
        );
        require(state == SigningCoordinator.SigningCohortState.TIMEOUT, "Request did not fail");

        InitiationRequest storage request = requests[cohortId];
        require(msg.sender == request.initiator, "Only initiator can request retry");
        address authority = signingCoordinator.getAuthority(cohortId);
        uint256 chainId = request.chainId;
        delete requests[cohortId];

        // we know that initiator already paid, so just try to create
        //  cohort again without processing payment.
        uint32 newCohortId = _createSigningCohort(authority, chainId);
        emit RetryFailedRequest(cohortId, newCohortId);
        return newCohortId;
    }

    function extendSigningCohort(uint32 cohortId) external {
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        InitiationRequest storage request = requests[cohortId];
        require(msg.sender == request.initiator, "Only initiator can extend cohort duration");
        _processPayment(msg.sender, defaultProviders.length, defaultDuration);

        signingCoordinator.extendSigningCohortDuration(cohortId, defaultDuration);
        emit ExtensionExecuted(cohortId, defaultDuration);
    }
}
