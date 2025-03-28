// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./EncryptorSlotsSubscription.sol";
import "../GlobalAllowList.sol";

/**
 * @title StandardSubscription
 * @notice Manages the subscription information for rituals.
 */
contract StandardSubscription is EncryptorSlotsSubscription, Initializable, OwnableUpgradeable {
    using SafeERC20 for IERC20;

    struct Billing {
        bool paid;
        uint128 encryptorSlots; // pre-paid encryptor slots for the billing period
    }

    uint32 public constant INACTIVE_RITUAL_ID = type(uint32).max;
    uint256 public constant INCREASE_BASE = 10000;

    GlobalAllowList public immutable accessController;
    IERC20 public immutable feeToken;
    address public immutable adopterSetter;

    uint256 public immutable initialBaseFeeRate;
    uint256 public immutable baseFeeRateIncrease;
    uint256 public immutable encryptorFeeRate;
    uint256 public immutable maxNodes;

    uint32 public activeRitualId;
    mapping(uint256 periodNumber => Billing billing) public billingInfo;
    address public adopter;

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
     * @param _accessController The address of the global allow list
     * @param _feeToken The address of the fee token contract
     * @param _adopterSetter Address that can set the adopter address
     * @param _initialBaseFeeRate Fee rate per node per second
     * @param _baseFeeRateIncrease Increase of base fee rate per each period (fraction of INCREASE_BASE)
     * @param _encryptorFeeRate Fee rate per encryptor per second
     * @param _maxNodes Maximum nodes in the package
     * @param _subscriptionPeriodDuration Maximum duration of subscription period
     * @param _yellowPeriodDuration Duration of yellow period
     * @param _redPeriodDuration Duration of red period
     */
    constructor(
        Coordinator _coordinator,
        GlobalAllowList _accessController,
        IERC20 _feeToken,
        address _adopterSetter,
        uint256 _initialBaseFeeRate,
        uint256 _baseFeeRateIncrease,
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
        require(_adopterSetter != address(0), "Adopter setter cannot be the zero address");
        require(
            address(_accessController) != address(0),
            "Access controller cannot be the zero address"
        );
        require(
            _baseFeeRateIncrease < INCREASE_BASE,
            "Base fee rate increase must be fraction of INCREASE_BASE"
        );
        feeToken = _feeToken;
        adopterSetter = _adopterSetter;
        initialBaseFeeRate = _initialBaseFeeRate;
        baseFeeRateIncrease = _baseFeeRateIncrease;
        encryptorFeeRate = _encryptorFeeRate;
        maxNodes = _maxNodes;
        accessController = _accessController;
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
    function initialize(address _treasury) external initializer {
        activeRitualId = INACTIVE_RITUAL_ID;
        __Ownable_init(_treasury);
    }

    function setAdopter(address _adopter) external {
        require(msg.sender == adopterSetter, "Only adopter setter can set adopter");
        require(
            adopter == address(0) && _adopter != address(0),
            "Adopter can be set only once with not zero address"
        );
        adopter = _adopter;
    }

    function baseFees() public view returns (uint256) {
        uint256 currentPeriodNumber = getCurrentPeriodNumber();
        return baseFees(currentPeriodNumber);
    }

    /// @dev potential overflow after 15-16 periods
    function baseFees(uint256 periodNumber) public view returns (uint256) {
        uint256 baseFeeRate = initialBaseFeeRate *
            (INCREASE_BASE + baseFeeRateIncrease) ** periodNumber;
        return
            (baseFeeRate * subscriptionPeriodDuration * maxNodes) / (INCREASE_BASE ** periodNumber);
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

        uint256 periodNumber = currentPeriodNumber;
        if (billingInfo[periodNumber].paid) {
            periodNumber++;
        }
        Billing storage billing = billingInfo[periodNumber];
        billing.paid = true;
        billing.encryptorSlots = encryptorSlots;

        uint256 fees = baseFees(periodNumber) +
            encryptorFees(encryptorSlots, subscriptionPeriodDuration);
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
     */
    function withdrawToTreasury() external {
        uint256 amount = feeToken.balanceOf(address(this));
        require(amount > 0, "Insufficient balance available");
        feeToken.safeTransfer(owner(), amount);
        emit WithdrawalToTreasury(owner(), amount);
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
                "Only failed/expired rituals allowed to be reinitiated"
            );
        }
        activeRitualId = ritualId;
    }
}
