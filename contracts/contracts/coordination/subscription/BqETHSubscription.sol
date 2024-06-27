// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./EncryptorSlotsSubscription.sol";

/**
 * @title BqETH Subscription
 * @notice Manages the subscription information for rituals.
 */
contract BqETHSubscription is EncryptorSlotsSubscription, Initializable, OwnableUpgradeable {
    using SafeERC20 for IERC20;

    struct Billing {
        bool paid;
        uint128 encryptorSlots; // pre-paid encryptor slots for the billing period
    }

    IERC20 public immutable feeToken;

    uint32 public constant INACTIVE_RITUAL_ID = type(uint32).max;

    address public immutable adopter;

    uint256 public immutable baseFeeRate;
    uint256 public immutable encryptorFeeRate;
    uint256 public immutable maxNodes;

    IEncryptionAuthorizer public accessController;
    uint32 public activeRitualId;
    mapping(uint256 periodNumber => Billing billing) public billingInfo;

    uint256[20] private gap;

    /**
     * @notice Emitted when a subscription is spent
     * @param treasury The address of the treasury
     * @param amount The amount withdrawn
     */
    event WithdrawalToTreasury(address indexed treasury, uint256 amount);

    /**
     * @notice Emitted when a subscription is paid
     * @param subscriber The address of the subscriber
     * @param amount The amount paid
     * @param encryptorSlots Number of encryptor slots
     * @param endOfSubscription End timestamp of subscription
     */
    event SubscriptionPaid(
        address indexed subscriber,
        uint256 amount,
        uint128 encryptorSlots,
        uint32 endOfSubscription
    );

    /**
     * @notice Emitted when additional encryptor slots are paid
     * @param sponsor The address that paid for the slots
     * @param amount The amount paid
     * @param encryptorSlots Number of encryptor slots
     * @param endOfCurrentPeriod End timestamp of the current billing period
     */
    event EncryptorSlotsPaid(
        address indexed sponsor,
        uint256 amount,
        uint128 encryptorSlots,
        uint32 endOfCurrentPeriod
    );

    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _feeToken The address of the fee token contract
     * @param _adopter The address of the adopter
     * @param _baseFeeRate Fee rate per node per second
     * @param _encryptorFeeRate Fee rate per encryptor per second
     * @param _maxNodes Maximum nodes in the package
     * @param _subscriptionPeriodDuration Maximum duration of subscription period
     * @param _yellowPeriodDuration Duration of yellow period
     * @param _redPeriodDuration Duration of red period
     */
    constructor(
        Coordinator _coordinator,
        IERC20 _feeToken,
        address _adopter,
        uint256 _baseFeeRate,
        uint256 _encryptorFeeRate,
        uint256 _maxNodes,
        uint32 _subscriptionPeriodDuration,
        uint32 _yellowPeriodDuration,
        uint32 _redPeriodDuration
    )
        EncryptorSlotsSubscription(
            _coordinator,
            _subscriptionPeriodDuration,
            _yellowPeriodDuration,
            _redPeriodDuration
        )
    {
        require(address(_feeToken) != address(0), "Fee token cannot be the zero address");
        require(_adopter != address(0), "Adopter cannot be the zero address");
        feeToken = _feeToken;
        adopter = _adopter;
        baseFeeRate = _baseFeeRate;
        encryptorFeeRate = _encryptorFeeRate;
        maxNodes = _maxNodes;
        _disableInitializers();
    }

    modifier onlyAccessController() override {
        require(
            msg.sender == address(accessController),
            "Only Access Controller can call this method"
        );
        _;
    }

    modifier onlyActiveRitual(uint32 ritualId) override {
        require(
            activeRitualId != INACTIVE_RITUAL_ID && ritualId == activeRitualId,
            "Ritual must be active"
        );
        _;
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(
        address _treasury,
        IEncryptionAuthorizer _accessController
    ) external initializer {
        require(
            address(accessController) == address(0) && address(_accessController) != address(0),
            "Access controller not already set and parameter cannot be the zero address"
        );
        accessController = _accessController;
        activeRitualId = INACTIVE_RITUAL_ID;
        __Ownable_init(_treasury);
    }

    function baseFees() public view returns (uint256) {
        return baseFeeRate * subscriptionPeriodDuration * maxNodes;
    }

    function encryptorFees(uint128 encryptorSlots, uint32 duration) public view returns (uint256) {
        return encryptorFeeRate * duration * encryptorSlots;
    }

    function isPeriodPaid(uint256 periodNumber) public view override returns (bool) {
        return billingInfo[periodNumber].paid;
    }

    function getPaidEncryptorSlots(uint256 periodNumber) public view override returns (uint256) {
        return billingInfo[periodNumber].encryptorSlots;
    }

    /**
     *
     * @notice Pays for the closest unpaid subscription period (either the current or the next)
     * @param encryptorSlots Number of slots for encryptors
     */
    function payForSubscription(uint128 encryptorSlots) external {
        uint256 currentPeriodNumber = getCurrentPeriodNumber();
        require(!billingInfo[currentPeriodNumber + 1].paid, "Next billing period already paid"); // TODO until we will have refunds
        require(
            startOfSubscription == 0 ||
                getEndOfSubscription() + yellowPeriodDuration + redPeriodDuration >=
                block.timestamp,
            "Subscription is over"
        );

        uint256 fees = baseFees() + encryptorFees(encryptorSlots, subscriptionPeriodDuration);
        uint256 periodNumber = currentPeriodNumber;
        if (billingInfo[periodNumber].paid) {
            periodNumber++;
        }
        Billing storage billing = billingInfo[periodNumber];
        billing.paid = true;
        billing.encryptorSlots = encryptorSlots;

        feeToken.safeTransferFrom(msg.sender, address(this), fees);
        emit SubscriptionPaid(msg.sender, fees, encryptorSlots, getEndOfSubscription());
    }

    /**
     * @notice Pays for additional encryptor slots in the current period
     * @param additionalEncryptorSlots Additional number of slots for encryptors
     */
    function payForEncryptorSlots(uint128 additionalEncryptorSlots) external {
        uint256 currentPeriodNumber = getCurrentPeriodNumber();
        Billing storage billing = billingInfo[currentPeriodNumber];
        require(billing.paid, "Current billing period must be paid");

        uint32 duration = subscriptionPeriodDuration;
        uint32 endOfCurrentPeriod = 0;
        if (startOfSubscription != 0) {
            endOfCurrentPeriod = uint32(
                startOfSubscription + (currentPeriodNumber + 1) * subscriptionPeriodDuration
            );
            duration = endOfCurrentPeriod - uint32(block.timestamp);
        }

        uint256 fees = encryptorFees(additionalEncryptorSlots, duration);
        billing.encryptorSlots += additionalEncryptorSlots;

        feeToken.safeTransferFrom(msg.sender, address(this), fees);
        emit EncryptorSlotsPaid(msg.sender, fees, additionalEncryptorSlots, endOfCurrentPeriod);
    }

    /**
     * @notice Withdraws the contract balance to the treasury
     * @param amount The amount to withdraw
     */
    function withdrawToTreasury(uint256 amount) external onlyOwner {
        require(amount <= feeToken.balanceOf(address(this)), "Insufficient balance available");
        feeToken.safeTransfer(msg.sender, amount);
        emit WithdrawalToTreasury(msg.sender, amount);
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256 numberOfProviders,
        uint32 duration
    ) external override onlyCoordinator {
        require(initiator == adopter, "Only adopter can initiate ritual");
        if (startOfSubscription == 0) {
            startOfSubscription = uint32(block.timestamp);
        }
        uint32 endOfSubscription = getEndOfSubscription();
        require(endOfSubscription != 0, "Subscription has to be paid first");
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
                "Only failed rituals allowed to be reinitiated"
            );
        }
        activeRitualId = ritualId;
    }
}
