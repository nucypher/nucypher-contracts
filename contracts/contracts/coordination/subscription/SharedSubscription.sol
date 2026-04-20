// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./EncryptorSlotsSubscription.sol";
import "../IEncryptionAuthorizer.sol";
import "../IFeeModel.sol";

/**
 * @title SharedSubscription
 * @notice Manages the subscription information for rituals.
 */
contract SharedSubscription is IFeeModel, Initializable, OwnableUpgradeable {
    using SafeERC20 for IERC20;

    struct AuthAdminInfo {
        uint32 startOfSubscription;
        uint256 usedEncryptorSlots;
        mapping(uint256 periodNumber => Billing billing) billingInfo;
    }

    struct Billing {
        bool paid;
        uint128 encryptorSlots; // pre-paid encryptor slots for the billing period
    }

    uint32 public constant INACTIVE_RITUAL_ID = type(uint32).max;

    Coordinator public immutable coordinator;
    IEncryptionAuthorizer public immutable accessController;
    IERC20 public immutable feeToken;

    uint32 public immutable subscriptionPackageDuration;
    uint32 public immutable subscriptionPackageEncryptors;
    address public immutable adopterSetter;

    uint256 public immutable baseFeeRate;
    uint256 public immutable encryptorFeeRate;

    uint32 public activeRitualId;
    mapping(address authAdmin => AuthAdminInfo authAdminStruct) public authAdminInfo;
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
     * @param authAdmin Autharization admin that was paid
     * @param amount The amount paid
     * @param encryptorSlots Number of encryptor slots
     * @param endOfSubscription End timestamp of subscription
     */
    event SubscriptionPaid(
        address indexed subscriber,
        address indexed authAdmin,
        uint256 amount,
        uint128 encryptorSlots,
        uint32 endOfSubscription
    );

    /**
     * @notice Emitted when additional encryptor slots are paid
     * @param sponsor The address that paid for the slots
     * @param authAdmin Autharization admin that was paid
     * @param amount The amount paid
     * @param encryptorSlots Number of encryptor slots
     * @param endOfCurrentPeriod End timestamp of the current billing period
     */
    event EncryptorSlotsPaid(
        address indexed sponsor,
        address indexed authAdmin,
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
     * @param _baseFeeRate Fee rate per node per second
     * @param _encryptorFeeRate Fee rate per encryptor per second
     * @param _subscriptionPackageDuration Duration of subscription package
     */
    constructor(
        Coordinator _coordinator,
        IEncryptionAuthorizer _accessController,
        IERC20 _feeToken,
        address _adopterSetter,
        uint256 _baseFeeRate,
        uint256 _encryptorFeeRate,
        uint32 _subscriptionPackageDuration
    ) {
        require(address(_feeToken) != address(0), "Fee token cannot be the zero address");
        require(_adopterSetter != address(0), "Adopter setter cannot be the zero address");
        require(
            address(_accessController) != address(0),
            "Access controller cannot be the zero address"
        );
        require(address(_coordinator) != address(0), "Coordinator cannot be the zero address");
        coordinator = _coordinator;
        feeToken = _feeToken;
        adopterSetter = _adopterSetter;
        baseFeeRate = _baseFeeRate;
        encryptorFeeRate = _encryptorFeeRate;
        accessController = _accessController;
        subscriptionPackageDuration = _subscriptionPackageDuration;
        _disableInitializers();
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

    modifier onlyCoordinator() {
        require(msg.sender == address(coordinator), "Only the Coordinator can call this method");
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

    /// @dev potential overflow after 15-16 periods
    function baseFees() public view returns (uint256) {
        return baseFeeRate * subscriptionPackageDuration;
    }

    function encryptorFees(uint128 encryptorSlots, uint32 duration) public view returns (uint256) {
        return encryptorFeeRate * duration * encryptorSlots;
    }

    function isPeriodPaid(address authAdmin, uint256 periodNumber) public view returns (bool) {
        return authAdminInfo[authAdmin].billingInfo[periodNumber].paid;
    }

    function getPaidEncryptorSlots(
        address authAdmin,
        uint256 periodNumber
    ) public view returns (uint256) {
        return authAdminInfo[authAdmin].billingInfo[periodNumber].encryptorSlots;
    }

    /**
     *
     * @notice Pays for the closest unpaid subscription period (either the current or the next)
     * @param encryptorPackages Number of encryptor packages
     */
    function payForSubscription(address authAdmin, uint32 encryptorPackages) external {
        uint256 fees = processPaymentForSubscription(authAdmin, encryptorPackages);
        feeToken.safeTransferFrom(msg.sender, address(this), fees);
    }

    /**
     * @notice Process payment for the closest unpaid subscription period (either the current or the next)
     * @param encryptorPackages Number of encryptor packages
     */
    function processPaymentForSubscription(
        address authAdmin,
        uint32 encryptorPackages
    ) internal returns (uint256 fees) {
        uint256 currentPeriodNumber = getCurrentPeriodNumber(authAdmin);
        AuthAdminInfo storage authAdminStruct = authAdminInfo[authAdmin];
        require(
            !authAdminStruct.billingInfo[currentPeriodNumber + 1].paid,
            "Next billing period already paid"
        ); // TODO until we will have refunds
        require(
            authAdminStruct.startOfSubscription == 0 ||
                getEndOfSubscription(authAdmin) >= block.timestamp,
            "Subscription is over"
        );

        uint256 periodNumber = currentPeriodNumber;
        if (authAdminStruct.billingInfo[periodNumber].paid) {
            periodNumber++;
        }
        Billing storage billing = authAdminStruct.billingInfo[periodNumber];
        billing.paid = true;
        billing.encryptorSlots = encryptorPackages * subscriptionPackageEncryptors;

        fees = baseFees() + encryptorFees(billing.encryptorSlots, subscriptionPackageDuration);
        emit SubscriptionPaid(
            msg.sender,
            authAdmin,
            fees,
            billing.encryptorSlots,
            getEndOfSubscription(authAdmin)
        );
    }

    /**
     * @notice Pays for additional encryptor slots in the current period
     * @param additionalEncryptorPackages Additional number of encryptor packages
     */
    function payForEncryptorSlots(address authAdmin, uint32 additionalEncryptorPackages) external {
        uint256 fees = processPaymentForEncryptorSlots(authAdmin, additionalEncryptorPackages);
        feeToken.safeTransferFrom(msg.sender, address(this), fees);
    }

    /**
     * @notice Process payment for additional encryptor slots in the current period
     * @param additionalEncryptorPackages Additional number of encryptor packages
     */
    function processPaymentForEncryptorSlots(
        address authAdmin,
        uint32 additionalEncryptorPackages
    ) internal returns (uint256 fees) {
        uint256 currentPeriodNumber = getCurrentPeriodNumber(authAdmin);
        AuthAdminInfo storage authAdminStruct = authAdminInfo[authAdmin];
        Billing storage billing = authAdminStruct.billingInfo[currentPeriodNumber];
        require(billing.paid, "Current billing period must be paid");

        uint32 duration = subscriptionPackageDuration;
        uint32 endOfCurrentPeriod = 0;
        if (authAdminStruct.startOfSubscription != 0) {
            endOfCurrentPeriod = uint32(
                authAdminStruct.startOfSubscription +
                    (currentPeriodNumber + 1) *
                    subscriptionPackageDuration
            );
            duration = endOfCurrentPeriod - uint32(block.timestamp);
        }

        uint128 additionalEncryptorSlots = additionalEncryptorPackages *
            subscriptionPackageEncryptors;
        uint256 fees = encryptorFees(additionalEncryptorSlots, duration);
        billing.encryptorSlots += additionalEncryptorSlots;

        emit EncryptorSlotsPaid(
            msg.sender,
            authAdmin,
            fees,
            additionalEncryptorSlots,
            endOfCurrentPeriod
        );
        return fees;
    }

    /**
     * @notice Withdraws the fees to the treasury
     */
    function withdrawToTreasury() external {
        uint256 amount = feeToken.balanceOf(address(this));
        require(0 < amount, "Insufficient balance available");
        feeToken.safeTransfer(owner(), amount);
        emit WithdrawalToTreasury(owner(), amount);
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256,
        uint32
    ) external onlyCoordinator {
        require(initiator == adopter, "Only adopter can initiate ritual");
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

    function getCurrentPeriodNumber(address authAdmin) public view returns (uint256) {
        AuthAdminInfo storage authAdminStruct = authAdminInfo[authAdmin];
        if (authAdminStruct.startOfSubscription == 0) {
            return 0;
        }
        return
            (block.timestamp - authAdminStruct.startOfSubscription) / subscriptionPackageDuration;
    }

    function getEndOfSubscription(
        address authAdmin
    ) public view returns (uint32 endOfSubscription) {
        AuthAdminInfo storage authAdminStruct = authAdminInfo[authAdmin];
        if (authAdminStruct.startOfSubscription == 0) {
            return 0;
        }

        uint256 currentPeriodNumber = getCurrentPeriodNumber(authAdmin);
        if (currentPeriodNumber == 0 && !isPeriodPaid(authAdmin, currentPeriodNumber)) {
            return 0;
        }

        if (isPeriodPaid(authAdmin, currentPeriodNumber)) {
            while (isPeriodPaid(authAdmin, currentPeriodNumber)) {
                currentPeriodNumber++;
            }
        } else {
            while (!isPeriodPaid(authAdmin, currentPeriodNumber)) {
                currentPeriodNumber--;
            }
            currentPeriodNumber++;
        }
        endOfSubscription = uint32(
            authAdminStruct.startOfSubscription + currentPeriodNumber * subscriptionPackageDuration
        );
    }

    function beforeSetAuthorization(
        address authAdmin,
        uint32,
        address[] calldata addresses,
        bool value
    ) public virtual {
        require(block.timestamp <= getEndOfSubscription(authAdmin), "Subscription has expired");
        AuthAdminInfo storage authAdminStruct = authAdminInfo[authAdmin];
        if (value) {
            uint256 currentPeriodNumber = getCurrentPeriodNumber(authAdmin);
            uint256 encryptorSlots = isPeriodPaid(authAdmin, currentPeriodNumber)
                ? getPaidEncryptorSlots(authAdmin, currentPeriodNumber)
                : 0;
            authAdminStruct.usedEncryptorSlots += addresses.length;
            require(
                authAdminStruct.usedEncryptorSlots <= encryptorSlots,
                "Encryptors slots filled up"
            );
        } else {
            if (authAdminStruct.usedEncryptorSlots >= addresses.length) {
                authAdminStruct.usedEncryptorSlots -= addresses.length;
            } else {
                authAdminStruct.usedEncryptorSlots = 0;
            }
        }
    }

    function beforeIsAuthorized(address authAdmin, uint32) public view virtual {
        require(block.timestamp <= getEndOfSubscription(authAdmin), "Subscription has expired");
        // used encryptor slots must be paid
        if (block.timestamp <= getEndOfSubscription(authAdmin)) {
            uint256 currentPeriodNumber = getCurrentPeriodNumber(authAdmin);
            require(
                authAdminInfo[authAdmin].usedEncryptorSlots <=
                    getPaidEncryptorSlots(authAdmin, currentPeriodNumber),
                "Encryptors slots filled up"
            );
        }
    }

    /**
     * @dev This function is called before the setAuthorizations function
     */
    function beforeSetAuthorization(uint32, address[] calldata, bool) public virtual override {
        revert("Unused");
    }

    /**
     * @dev This function is called before the isAuthorized function
     */
    function beforeIsAuthorized(uint32) public view virtual override {
        revert("Unused");
    }

    function processRitualExtending(
        address initiator,
        uint32 ritualId,
        uint256,
        uint32
    ) external view override onlyCoordinator onlyActiveRitual(ritualId) {
        require(initiator == adopter, "Only adopter can extend ritual");
    }
}
