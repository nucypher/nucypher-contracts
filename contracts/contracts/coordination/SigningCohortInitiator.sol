// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./SigningCoordinator.sol";

contract SigningCohortInitiator is OwnableUpgradeable {
    using SafeERC20 for IERC20;

    event RequestExecuted(
        uint32 indexed cohortId,
        address indexed initiator,
        address authority,
        uint256 chainId
    );

    event RetryFailedRequest(uint32 indexed oldCohortId, uint32 indexed newCohortId);

    event AdditionalChainDeployed(uint32 indexed cohortId, uint256 chainId);

    event ExtensionExecuted(uint32 indexed cohortId, uint32 additionalDuration);

    event DefaultParametersUpdated(address[] providers, uint16 threshold, uint32 duration);

    event FeeRateUpdated(uint256 oldFeeRate, uint256 newFeeRate);

    struct InitiationRequest {
        address initiator;
        uint256 chainId;
    }

    SigningCoordinator public immutable signingCoordinator;
    IERC20 public immutable currency;

    uint256 public feeRatePerSecond;
    address[] public defaultProviders;
    uint16 public defaultThreshold;
    uint32 public defaultDuration;

    mapping(uint32 => InitiationRequest) public requests; // cohortId -> Request

    constructor(SigningCoordinator _signingCoordinator, IERC20 _currency) {
        require(address(_signingCoordinator) != address(0), "Invalid signing coordinator");
        require(address(_currency) != address(0), "Invalid currency");
        signingCoordinator = _signingCoordinator;
        currency = _currency;
        _disableInitializers();
    }

    /**
     * @notice Initialize function for use with OpenZeppelin proxy
     */
    function initialize() external initializer {
        __Ownable_init(msg.sender);
    }

    function _ensureSortedProviders(address[] memory providers) internal pure {
        address previous = address(0);
        for (uint256 i = 0; i < providers.length; i++) {
            require(providers[i] != address(0), "Invalid provider address");
            require(providers[i] > previous, "Providers must be sorted");
            previous = providers[i];
        }
    }

    function _processPayment(address initiator) internal {
        uint256 cohortCost = getCohortCost();
        require(cohortCost > 0, "Invalid cohort cost");
        currency.safeTransferFrom(initiator, address(this), cohortCost);
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

    function getCohortCost() public view returns (uint256) {
        return feeRatePerSecond * defaultProviders.length * defaultDuration;
    }

    function withdrawFees() external onlyOwner {
        uint256 fees = currency.balanceOf(address(this));
        require(fees > 0, "No fees to withdraw");
        currency.safeTransfer(msg.sender, fees);
    }

    function establishSigningCohort(address authority, uint256 chainId) external returns (uint32) {
        _processPayment(msg.sender);
        return _createSigningCohort(authority, chainId);
    }

    function deployAdditionalChain(uint32 cohortId, uint256 chainId) external {
        InitiationRequest storage request = requests[cohortId];
        require(request.initiator != address(0), "Invalid cohort ID");
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        require(msg.sender == request.initiator, "Only initiator can deploy additional chain");
        require(request.chainId != chainId, "Chain ID already exists for this cohort");

        // TODO: do we want additional payment here?
        signingCoordinator.deployAdditionalChainForSigningMultisig(chainId, cohortId);
        emit AdditionalChainDeployed(cohortId, chainId);
    }

    function retryFailedRequest(uint32 cohortId) external returns (uint32) {
        InitiationRequest storage request = requests[cohortId];
        require(request.initiator != address(0), "Invalid cohort ID");

        SigningCoordinator.SigningCohortState state = signingCoordinator.getSigningCohortState(
            cohortId
        );
        require(state == SigningCoordinator.SigningCohortState.TIMEOUT, "Request did not fail");

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
        InitiationRequest storage request = requests[cohortId];
        require(request.initiator != address(0), "Invalid cohort ID");
        require(signingCoordinator.isCohortActive(cohortId), "Cohort is not active");
        require(msg.sender == request.initiator, "Only initiator can extend cohort duration");
        // TODO: do we charge a different fee for extension?
        _processPayment(msg.sender);

        signingCoordinator.extendSigningCohortDuration(cohortId, defaultDuration);
        emit ExtensionExecuted(cohortId, defaultDuration);
    }

    function setDefaultParameters(
        address[] memory providers,
        uint16 threshold,
        uint32 duration
    ) external onlyOwner {
        require(providers.length > 0, "Invalid default providers");
        require(threshold > 0 && threshold <= providers.length, "Invalid default threshold");
        require(duration > 0, "Invalid default duration");
        _ensureSortedProviders(providers);

        defaultProviders = providers;
        defaultThreshold = threshold;
        defaultDuration = duration;
        emit DefaultParametersUpdated(providers, threshold, duration);
    }

    function setFeeRate(uint256 _feeRatePerSecond) external onlyOwner {
        require(_feeRatePerSecond > 0, "Invalid fee rate");
        emit FeeRateUpdated(feeRatePerSecond, _feeRatePerSecond);
        feeRatePerSecond = _feeRatePerSecond;
    }
}
