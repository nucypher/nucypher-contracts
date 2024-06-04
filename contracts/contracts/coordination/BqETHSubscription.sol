// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./Coordinator.sol";
import "./IFeeModel.sol";

using SafeERC20 for IERC20;

/**
 * @title BqETH Subscription
 * @notice Manages the subscription information for rituals.
 */
contract BqETHSubscription is IFeeModel {
    Coordinator public immutable coordinator;
    IERC20 public immutable feeToken;

    uint32 public constant INACTIVE_RITUAL_ID = type(uint32).max;

    // TODO: DAO Treasury
    // TODO: Should it be updatable?
    address public immutable beneficiary;
    address public immutable adopter;

    uint256 public immutable feeRate;
    uint256 public immutable maxNodes;
    uint32 public immutable maxDuration;
    uint32 public immutable yellowPeriodDuration;
    uint32 public immutable redPeriodDuration;

    IEncryptionAuthorizer public accessController;

    uint32 public endOfSubscription;
    uint32 public activeRitualId;

    /**
     * @notice Emitted when a subscription is spent
     * @param beneficiary The address of the beneficiary
     * @param amount The amount withdrawn
     */
    event WithdrawalToBeneficiary(address indexed beneficiary, uint256 amount);

    /**
     * @notice Emitted when a subscription is paid
     * @param subscriber The address of the subscriber
     * @param amount The amount paid
     */
    event SubscriptionPaid(address indexed subscriber, uint256 amount);

    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _feeToken The address of the fee token contract
     * @param _beneficiary The address of the beneficiary
     * @param _adopter The address of the adopter
     * @param _feeRate Fee rate per node per second
     * @param _maxNodes Maximum nodes in the package
     * @param _maxDuration Maximum duration of ritual
     * @param _yellowPeriodDuration Duration of yellow period
     * @param _redPeriodDuration Duration of red period
     */
    constructor(
        Coordinator _coordinator,
        IERC20 _feeToken,
        address _beneficiary,
        address _adopter,
        uint256 _feeRate,
        uint256 _maxNodes,
        uint32 _maxDuration,
        uint32 _yellowPeriodDuration,
        uint32 _redPeriodDuration
    ) {
        require(address(_coordinator) != address(0), "Coordinator cannot be the zero address");
        require(address(_feeToken) != address(0), "Fee token cannot be the zero address");
        require(_beneficiary != address(0), "Beneficiary cannot be the zero address");
        require(_adopter != address(0), "Adopter cannot be the zero address");
        coordinator = _coordinator;
        feeToken = _feeToken;
        beneficiary = _beneficiary;
        adopter = _adopter;
        feeRate = _feeRate;
        maxNodes = _maxNodes;
        maxDuration = _maxDuration;
        yellowPeriodDuration = _yellowPeriodDuration;
        redPeriodDuration = _redPeriodDuration;
    }

    modifier onlyCoordinator() {
        require(msg.sender == address(coordinator), "Only the Coordinator can call this method");
        _;
    }

    modifier onlyBeneficiary() {
        require(msg.sender == beneficiary, "Only the beneficiary can call this method");
        _;
    }

    modifier onlyAccessController() {
        require(
            msg.sender == address(accessController),
            "Only Access Controller can call this method"
        );
        _;
    }

    modifier onlyActiveRitual(uint32 ritualId) {
        require(
            activeRitualId != INACTIVE_RITUAL_ID && ritualId == activeRitualId,
            "Ritual must be active"
        );
        _;
    }

    function initialize(IEncryptionAuthorizer _accessController) external {
        require(
            address(accessController) == address(0) && address(_accessController) != address(0),
            "Access controller cannot be the zero address"
        );
        accessController = _accessController;
        activeRitualId = INACTIVE_RITUAL_ID;
    }

    function packageFees() public view returns (uint256) {
        return feeRate * maxDuration * maxNodes;
    }

    /**
     * @notice Pays for a subscription
     */
    function paySubscriptionFor() external {
        // require(endOfSubscription == 0, "Subscription already payed");
        uint256 amount = packageFees();
        if (endOfSubscription == 0) {
            endOfSubscription = uint32(block.timestamp);
        }
        endOfSubscription += uint32(maxDuration);

        feeToken.safeTransferFrom(msg.sender, address(this), amount);
        emit SubscriptionPaid(msg.sender, amount);
    }

    /**
     * @notice Withdraws the contract balance to the beneficiary
     * @param amount The amount to withdraw
     */
    function withdrawToBeneficiary(uint256 amount) external onlyBeneficiary {
        require(amount <= feeToken.balanceOf(address(this)), "Insufficient available amount");
        feeToken.safeTransfer(beneficiary, amount);
        emit WithdrawalToBeneficiary(beneficiary, amount);
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external override onlyCoordinator {
        require(initiator == adopter, "Only adopter can initiate ritual");
        require(endOfSubscription != 0, "Subscription has to be payed first");
        require(
            endOfSubscription + yellowPeriodDuration + redPeriodDuration >=
                block.timestamp + duration &&
                numberOfProviders <= maxNodes,
            "Ritual parameters exceed available in package"
        );
        require(
            address(accessController) != address(0) &&
                accessController == coordinator.getAccessController(ritualId),
            "Access controller for ritual must be approved"
        );

        if (activeRitualId != INACTIVE_RITUAL_ID) {
            Coordinator.RitualState state = coordinator.getRitualState(activeRitualId);
            require(
                state == Coordinator.RitualState.DKG_INVALID ||
                    state == Coordinator.RitualState.DKG_TIMEOUT ||
                    state == Coordinator.RitualState.EXPIRED, // TODO check if it's ok
                "Only failed rituals allowed to be reinitiate"
            );
        }
        activeRitualId = ritualId;
    }

    function processRitualExtending(
        address,
        uint32 ritualId,
        uint256,
        uint32
    ) external view override onlyCoordinator onlyActiveRitual(ritualId) {
        (, uint32 endTimestamp) = coordinator.getTimestamps(ritualId);
        require(
            endOfSubscription + yellowPeriodDuration + redPeriodDuration >= endTimestamp,
            "Ritual parameters exceed available in package"
        );
    }

    /**
     * @dev This function is called before the setAuthorizations function
     */
    function beforeSetAuthorization(
        uint32 ritualId,
        address[] calldata,
        bool
    ) external view override onlyAccessController onlyActiveRitual(ritualId) {
        require(block.timestamp <= endOfSubscription, "Subscription has expired");
    }
}
